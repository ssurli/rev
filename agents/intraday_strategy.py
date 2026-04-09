"""IntradayStrategyAgent — generates intraday BUY / SELL / TRIM signals.

Entry logic — LONG (BUY):
  ✓ intraday_score  ≥  score_threshold (default 0.40)
  ✓ ema_cross in ("bullish_cross", "above")
  ✓ RSI(5)          <  rsi_overbought  (default 65)
  ✓ stoch_k         >  stoch_d         (momentum aligned)
  ✓ trend_1h        == "bullish"       (multi-timeframe confirmation)
  ✓ price_vs_vwap   > -1.5%            (not too far below equilibrium)
  ✓ sufficient cash in portfolio

Exit — stop-loss:
  price ≤ entry_price - ATR * stop_atr_multiplier

Exit — take-profit:
  price ≥ entry_price + ATR * take_atr_multiplier

Exit — reversal:
  intraday_score ≤ -0.30 AND ema below AND RSI > 70

Bearish signal — TRIM existing swing position:
  All bearish conditions AND position exists in swing portfolio
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_CFG_PATH = Path(__file__).parent.parent / "config.json"


def _load_dt_config() -> dict:
    try:
        with open(_CFG_PATH) as f:
            return json.load(f).get("day_trading", {})
    except Exception:
        return {}


def _has_swing_position(symbol: str, portfolio: dict) -> bool:
    return any(p["symbol"] == symbol for p in portfolio.get("positions", []))


def run(state: dict) -> dict:
    """Generate intraday trading signals from computed indicators."""
    indicators: dict[str, dict] = state.get("intraday_indicators", {})
    session:    dict             = state.get("dt_session", {})
    portfolio:  dict             = state.get("portfolio", {})
    dt_cfg:     dict             = _load_dt_config()

    if not dt_cfg.get("enabled", False):
        state["intraday_signals"] = []
        return state

    # --- Config params ---
    score_threshold  = float(dt_cfg.get("score_threshold",          0.40))
    rsi_overbought   = float(dt_cfg.get("rsi_overbought",           65.0))
    rsi_oversold     = float(dt_cfg.get("rsi_oversold",             35.0))
    stop_atr_mult    = float(dt_cfg.get("stop_loss_atr_multiplier",  1.5))
    take_atr_mult    = float(dt_cfg.get("take_profit_atr_multiplier",2.5))
    pos_size_pct     = float(dt_cfg.get("position_size_pct",         2.0))
    max_pos_eur      = float(dt_cfg.get("max_position_eur",        100.0))
    max_trades       = int(  dt_cfg.get("max_daily_trades",           10))
    max_loss_pct     = float(dt_cfg.get("max_daily_loss_pct",        -2.0))
    max_concurrent   = int(  dt_cfg.get("max_concurrent_positions",    3))

    # --- Session state ---
    trades_today          = session.get("trades_today", 0)
    daily_pnl_pct         = session.get("daily_pnl_pct", 0.0)
    cooldown_symbols: dict= session.get("cooldown_symbols", {})
    open_positions:   dict= session.get("open_intraday_positions", {})

    total_eur = portfolio.get("total_value_eur", 1000.0)
    cash_eur  = portfolio.get("cash_eur", 0.0)

    signals: list[dict] = []

    # --- Circuit breakers ---
    if trades_today >= max_trades:
        logger.info("IntradayStrategy: max daily trades reached (%d)", max_trades)
        state["intraday_signals"] = []
        return state

    if daily_pnl_pct <= max_loss_pct:
        logger.warning("IntradayStrategy: daily loss limit hit (%.2f%% ≤ %.2f%%)",
                       daily_pnl_pct, max_loss_pct)
        state["intraday_signals"] = []
        return state

    now_ts = datetime.now(timezone.utc).timestamp()

    for sym, ind in indicators.items():
        price        = ind["price"]
        atr          = ind["atr"]
        score        = ind["intraday_score"]
        ema_cross    = ind["ema_cross"]
        rsi5         = ind["rsi5"]
        stoch_k      = ind["stoch_k"]
        stoch_d      = ind["stoch_d"]
        trend_1h     = ind["trend_1h"]
        price_vs_vwap= ind["price_vs_vwap"]

        # Per-symbol cooldown check
        if now_ts < cooldown_symbols.get(sym, 0):
            remaining = int((cooldown_symbols[sym] - now_ts) / 60)
            logger.debug("IntradayStrategy: %s cooldown — %d min left", sym, remaining)
            continue

        in_position = sym in open_positions

        # ----------------------------------------------------------------
        # A) Manage existing intraday position
        # ----------------------------------------------------------------
        if in_position:
            pos          = open_positions[sym]
            entry_price  = pos["entry_price"]
            sl           = pos["stop_loss"]
            tp           = pos["take_profit"]
            amount_eur   = pos["amount_eur"]

            if price <= sl:
                signals.append({
                    "symbol": sym, "action": "SELL", "confidence": 1.0,
                    "amount_eur": amount_eur, "price_eur": price,
                    "stop_loss": sl, "take_profit": tp,
                    "reason": f"DT Stop-loss: {price:.4f} ≤ SL {sl:.4f}  "
                              f"(entry {entry_price:.4f})",
                    "intraday_score": score, "cycle": "intraday",
                    "trigger": "stop_loss",
                })
                continue

            if price >= tp:
                signals.append({
                    "symbol": sym, "action": "SELL", "confidence": 1.0,
                    "amount_eur": amount_eur, "price_eur": price,
                    "stop_loss": sl, "take_profit": tp,
                    "reason": f"DT Take-profit: {price:.4f} ≥ TP {tp:.4f}  "
                              f"(entry {entry_price:.4f})",
                    "intraday_score": score, "cycle": "intraday",
                    "trigger": "take_profit",
                })
                continue

            # Bearish reversal exit
            if score <= -0.30 and ema_cross in ("bearish_cross", "below") and rsi5 > 70:
                signals.append({
                    "symbol": sym, "action": "SELL", "confidence": 0.80,
                    "amount_eur": amount_eur, "price_eur": price,
                    "stop_loss": sl, "take_profit": tp,
                    "reason": f"DT Reversal exit: score={score:.2f}  RSI={rsi5:.1f}  "
                              f"EMA={ema_cross}",
                    "intraday_score": score, "cycle": "intraday",
                    "trigger": "reversal",
                })
            continue  # don't look for new entry while in position

        # ----------------------------------------------------------------
        # B) New LONG entry
        # ----------------------------------------------------------------
        if len(open_positions) >= max_concurrent:
            logger.debug("IntradayStrategy: max concurrent positions (%d) — skipping %s",
                         max_concurrent, sym)
            continue

        bullish_entry = (
            score        >= score_threshold and
            ema_cross    in ("bullish_cross", "above") and
            rsi5         <  rsi_overbought and
            stoch_k      >  stoch_d and
            trend_1h     == "bullish" and
            price_vs_vwap > -1.5
        )

        if bullish_entry:
            amount_eur = min(max_pos_eur, total_eur * pos_size_pct / 100.0)
            if amount_eur > cash_eur:
                logger.debug("IntradayStrategy: %s — insufficient cash (need €%.2f have €%.2f)",
                             sym, amount_eur, cash_eur)
                continue

            sl  = round(price - atr * stop_atr_mult,  4)
            tp  = round(price + atr * take_atr_mult,   4)
            sl_pct = round((sl - price) / price * 100, 2)
            tp_pct = round((tp - price) / price * 100, 2)
            rr     = round(abs(tp_pct / sl_pct), 2) if sl_pct != 0 else 0.0

            signals.append({
                "symbol": sym, "action": "BUY",
                "confidence": round(min(1.0, score), 2),
                "amount_eur": round(amount_eur, 2),
                "price_eur": price,
                "stop_loss": sl, "take_profit": tp,
                "reason": (
                    f"DT BUY: score={score:+.2f}  EMA={ema_cross}  "
                    f"RSI={rsi5:.1f}  VWAP{price_vs_vwap:+.2f}%  "
                    f"SL={sl_pct:.1f}%  TP={tp_pct:.1f}%  R:R={rr}"
                ),
                "intraday_score": score, "cycle": "intraday",
                "trigger": "entry",
            })
            continue

        # ----------------------------------------------------------------
        # C) Bearish TRIM of existing swing position
        # ----------------------------------------------------------------
        bearish_trim = (
            score        <= -score_threshold and
            ema_cross    in ("bearish_cross", "below") and
            rsi5         >  rsi_oversold and
            stoch_k      <  stoch_d and
            trend_1h     == "bearish" and
            _has_swing_position(sym, portfolio)
        )

        if bearish_trim:
            amount_eur = min(max_pos_eur, total_eur * pos_size_pct / 100.0)
            sl_bear = round(price + atr * stop_atr_mult, 4)
            tp_bear = round(price - atr * take_atr_mult, 4)
            signals.append({
                "symbol": sym, "action": "TRIM",
                "confidence": round(min(1.0, abs(score)), 2),
                "amount_eur": round(amount_eur, 2),
                "price_eur": price,
                "stop_loss": sl_bear, "take_profit": tp_bear,
                "reason": (
                    f"DT TRIM: score={score:+.2f}  EMA={ema_cross}  "
                    f"RSI={rsi5:.1f}  VWAP{price_vs_vwap:+.2f}%"
                ),
                "intraday_score": score, "cycle": "intraday",
                "trigger": "bearish_trim",
            })

    buy_n  = sum(1 for s in signals if s["action"] == "BUY")
    sell_n = sum(1 for s in signals if s["action"] in ("SELL", "TRIM"))
    logger.info(
        "IntradayStrategy: %d signals  BUY=%d  SELL/TRIM=%d  "
        "(trades_today=%d  daily_pnl=%.2f%%)",
        len(signals), buy_n, sell_n, trades_today, daily_pnl_pct,
    )

    state["intraday_signals"] = signals
    return state
