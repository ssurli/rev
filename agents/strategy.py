"""StrategyAgent — genera segnali BUY/SELL/TRIM/HOLD.

Logica multi-fattore (v2):
  forecast_score = (sentiment * 0.40) + (tech_score * 0.40) + (momentum * 0.20)

  BUY   se forecast_score > +0.35 AND confidence > 0.50 AND direction == BULLISH
  SELL  se forecast_score < -0.35 AND confidence > 0.50 AND direction == BEARISH
  TRIM  se posizione overweight >20% OPPURE P&L ≥ +30% (take-profit)
  SELL  (stop-loss) se P&L ≤ -15%
  HOLD  altrimenti
"""

from __future__ import annotations

import logging

from core.config import (
    ASSETS,
    MAX_POSITION_PCT,
    MAX_TRADE_EUR,
    MIN_CASH_PCT,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
)
from core.state import AssetForecast, BotState, PortfolioSnapshot, TradingSignal

logger = logging.getLogger(__name__)

_BUY_THRESHOLD  = 0.35
_SELL_THRESHOLD = -0.35
_MIN_CONFIDENCE = 0.50
_PRICE_SURGE_GUARD = 3.0   # non comprare se già salito >3% in 1h


def _position_pnl(sym: str, portfolio: PortfolioSnapshot) -> float | None:
    for pos in portfolio.get("positions", []):
        if pos["symbol"] == sym:
            return pos.get("pnl_pct", 0.0)
    return None


def _position_weight(sym: str, portfolio: PortfolioSnapshot) -> float:
    total = portfolio.get("total_value_eur", 0.0)
    if total <= 0:
        return 0.0
    for pos in portfolio.get("positions", []):
        if pos["symbol"] == sym:
            return pos.get("value_eur", 0.0) / total * 100.0
    return 0.0


def run(state: BotState) -> BotState:
    forecasts = state.get("forecasts", {})
    market    = state.get("market_data", {})
    portfolio = state.get("portfolio", {})
    total_eur = portfolio.get("total_value_eur", 0.0)
    cash_eur  = portfolio.get("cash_eur", 0.0)

    signals: list[TradingSignal] = []

    for sym in ASSETS:
        fc: AssetForecast | None = forecasts.get(sym)
        md = market.get(sym)
        if md is None:
            continue

        price      = md["price_eur"]
        change_1h  = (price - md["price_1h_ago"]) / md["price_1h_ago"] * 100.0 if md["price_1h_ago"] else 0.0
        pnl        = _position_pnl(sym, portfolio)
        weight     = _position_weight(sym, portfolio)

        forecast_score = fc["forecast_score"] if fc else 0.0
        confidence     = fc["confidence"]     if fc else 0.0
        direction      = fc["direction"]      if fc else "NEUTRAL"
        reasoning      = fc["reasoning"]      if fc else ""
        sentiment_s    = fc["sentiment_score"] if fc else 0.0

        # --- stop-loss ---
        if pnl is not None and pnl <= STOP_LOSS_PCT:
            signals.append(TradingSignal(
                symbol=sym, action="SELL", confidence=1.0,
                amount_eur=min(MAX_TRADE_EUR, total_eur * 0.05),
                reason=f"Stop-loss: P&L={pnl:.1f}%",
                sentiment_score=sentiment_s, forecast_score=forecast_score, price_eur=price,
            ))
            continue

        # --- take-profit / overweight trim ---
        if pnl is not None and (pnl >= TAKE_PROFIT_PCT or weight > MAX_POSITION_PCT):
            reason = (f"Take-profit: P&L={pnl:.1f}%"
                      if pnl >= TAKE_PROFIT_PCT
                      else f"Overweight: {weight:.1f}%>{MAX_POSITION_PCT}%")
            signals.append(TradingSignal(
                symbol=sym, action="TRIM", confidence=0.85,
                amount_eur=min(MAX_TRADE_EUR, total_eur * 0.03),
                reason=reason,
                sentiment_score=sentiment_s, forecast_score=forecast_score, price_eur=price,
            ))
            continue

        # --- BUY ---
        if forecast_score >= _BUY_THRESHOLD and confidence >= _MIN_CONFIDENCE and direction == "BULLISH":
            if change_1h > _PRICE_SURGE_GUARD:
                signals.append(TradingSignal(
                    symbol=sym, action="HOLD", confidence=confidence,
                    amount_eur=0.0,
                    reason=f"BUY bloccato: già salito {change_1h:.1f}% in 1h",
                    sentiment_score=sentiment_s, forecast_score=forecast_score, price_eur=price,
                ))
                continue
            if cash_eur / max(total_eur, 1) * 100.0 < MIN_CASH_PCT:
                signals.append(TradingSignal(
                    symbol=sym, action="HOLD", confidence=confidence,
                    amount_eur=0.0,
                    reason=f"BUY bloccato: cash sotto {MIN_CASH_PCT}%",
                    sentiment_score=sentiment_s, forecast_score=forecast_score, price_eur=price,
                ))
                continue
            amount = min(MAX_TRADE_EUR, cash_eur * 0.10)
            signals.append(TradingSignal(
                symbol=sym, action="BUY", confidence=round(confidence, 2),
                amount_eur=round(amount, 2),
                reason=f"BULLISH: score={forecast_score:.2f} conf={confidence:.0%} — {reasoning[:80]}",
                sentiment_score=sentiment_s, forecast_score=forecast_score, price_eur=price,
            ))

        # --- SELL ---
        elif forecast_score <= _SELL_THRESHOLD and confidence >= _MIN_CONFIDENCE and direction == "BEARISH":
            if pnl is None:
                continue  # non in posizione
            signals.append(TradingSignal(
                symbol=sym, action="SELL", confidence=round(confidence, 2),
                amount_eur=min(MAX_TRADE_EUR, total_eur * 0.05),
                reason=f"BEARISH: score={forecast_score:.2f} conf={confidence:.0%} — {reasoning[:80]}",
                sentiment_score=sentiment_s, forecast_score=forecast_score, price_eur=price,
            ))

        # --- HOLD ---
        else:
            signals.append(TradingSignal(
                symbol=sym, action="HOLD", confidence=round(confidence, 2),
                amount_eur=0.0,
                reason=f"NEUTRAL: score={forecast_score:.2f} dir={direction}",
                sentiment_score=sentiment_s, forecast_score=forecast_score, price_eur=price,
            ))

    logger.info("Strategy: %d signals (%s)",
                len(signals),
                {a: sum(1 for s in signals if s["action"] == a) for a in ("BUY","SELL","TRIM","HOLD")})

    state["signals"] = signals
    return state
