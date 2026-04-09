"""SessionManager — day trading session state and market-hours filter.

Responsibilities:
  - Reset session at start of each trading day
  - Filter symbols to market-open only (NYSE for stocks, 24/7 for crypto)
  - Track daily P&L and trade count (circuit breakers)
  - Manage per-symbol cooldown after stop-loss events
  - Track open intraday positions (entry, SL, TP)
  - Register order outcomes and update daily stats

State is kept in-memory (module-level dict).
A new trading day triggers automatic reset.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_CFG_PATH = Path(__file__).parent.parent / "config.json"

_NYSE_TZ = ZoneInfo("America/New_York")

_CRYPTO_SYMBOLS: frozenset[str] = frozenset({
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD",
    "ADA-USD", "DOGE-USD", "AVAX-USD", "DOT-USD", "MATIC-USD",
    "LINK-USD", "LTC-USD", "UNI-USD", "ATOM-USD", "NEAR-USD",
})

# ---------------------------------------------------------------------------
# In-memory session state
# ---------------------------------------------------------------------------

_session: dict = {
    "date":                     "",
    "trades_today":             0,
    "daily_pnl_eur":            0.0,
    "daily_pnl_pct":            0.0,
    "cooldown_symbols":         {},   # sym → unix timestamp (expire)
    "open_intraday_positions":  {},   # sym → position dict
    "closed_today":             [],   # list of closed trade results
}


def _load_dt_config() -> dict:
    try:
        with open(_CFG_PATH) as f:
            return json.load(f).get("day_trading", {})
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

def _reset_if_new_day() -> None:
    global _session
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _session["date"] != today:
        logger.info("SessionManager: new trading day %s — session reset", today)
        _session = {
            "date":                    today,
            "trades_today":            0,
            "daily_pnl_eur":           0.0,
            "daily_pnl_pct":           0.0,
            "cooldown_symbols":        {},
            "open_intraday_positions": {},
            "closed_today":            [],
        }


# ---------------------------------------------------------------------------
# Market hours
# ---------------------------------------------------------------------------

def is_market_open(symbol: str, dt_cfg: dict | None = None) -> bool:
    """Return True if trading is currently allowed for this symbol."""
    if symbol in _CRYPTO_SYMBOLS:
        return True  # crypto: 24/7

    if dt_cfg is None:
        dt_cfg = _load_dt_config()

    now_ny  = datetime.now(_NYSE_TZ)
    weekday = now_ny.weekday()
    if weekday >= 5:  # weekend
        return False

    mh = dt_cfg.get("market_hours", {}).get("stocks", {})
    open_str  = mh.get("open",  "09:30")
    close_str = mh.get("close", "16:00")
    oh, om    = map(int, open_str.split(":"))
    ch, cm    = map(int, close_str.split(":"))
    t_open    = time(oh, om)
    t_close   = time(ch, cm)
    return t_open <= now_ny.time() <= t_close


# ---------------------------------------------------------------------------
# Position / order management
# ---------------------------------------------------------------------------

def add_cooldown(symbol: str, minutes: int = 30) -> None:
    """Mark symbol as in cooldown for N minutes (typically after stop-loss)."""
    until = datetime.now(timezone.utc).timestamp() + minutes * 60
    _session["cooldown_symbols"][symbol] = until
    logger.info("SessionManager: cooldown %s for %d min", symbol, minutes)


def register_order(
    symbol:      str,
    action:      str,
    amount_eur:  float,
    price:       float,
    stop_loss:   float,
    take_profit: float,
) -> None:
    """Update session state after an order is filled."""
    _reset_if_new_day()

    if action == "BUY":
        _session["open_intraday_positions"][symbol] = {
            "entry_price": price,
            "stop_loss":   stop_loss,
            "take_profit": take_profit,
            "amount_eur":  amount_eur,
            "opened_at":   datetime.now(timezone.utc).isoformat(),
            "pnl_pct":     0.0,
        }
        _session["trades_today"] += 1
        logger.info(
            "SessionManager: OPEN  %s @ %.4f  SL=%.4f  TP=%.4f  €%.2f",
            symbol, price, stop_loss, take_profit, amount_eur,
        )

    elif action in ("SELL", "TRIM"):
        pos = _session["open_intraday_positions"].pop(symbol, None)
        _session["trades_today"] += 1

        if pos:
            entry   = pos["entry_price"]
            pnl_pct = (price - entry) / entry * 100
            pnl_eur = amount_eur * pnl_pct / 100
            _session["daily_pnl_eur"] += pnl_eur

            # Running average of per-trade pnl%
            n = len(_session["closed_today"]) + 1
            _session["daily_pnl_pct"] = (
                (_session["daily_pnl_pct"] * (n - 1) + pnl_pct) / n
            )

            _session["closed_today"].append({
                "symbol":  symbol,
                "entry":   round(entry, 4),
                "exit":    round(price, 4),
                "pnl_pct": round(pnl_pct, 2),
                "pnl_eur": round(pnl_eur, 2),
                "action":  action,
                "closed_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.info(
                "SessionManager: CLOSE %s @ %.4f  P&L=%+.2f%%  €%+.2f",
                symbol, price, pnl_pct, pnl_eur,
            )


def update_position_pnl(symbol: str, current_price: float) -> None:
    """Refresh the unrealised P&L% for an open intraday position."""
    pos = _session["open_intraday_positions"].get(symbol)
    if pos:
        entry = pos["entry_price"]
        pos["pnl_pct"] = round((current_price - entry) / entry * 100, 2)


def get_session() -> dict:
    """Return a snapshot of the current session state."""
    _reset_if_new_day()
    return dict(_session)


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

def run(state: dict) -> dict:
    """Filter tradeable symbols by market hours and inject session into state."""
    dt_cfg  = _load_dt_config()
    _reset_if_new_day()

    symbols: list[str] = state.get("dt_symbols", [])

    tradeable = [s for s in symbols if is_market_open(s, dt_cfg)]
    excluded  = set(symbols) - set(tradeable)
    if excluded:
        logger.info("SessionManager: market closed for %s", sorted(excluded))

    # Refresh unrealised P&L for open positions using latest indicator prices
    for sym, pos in _session["open_intraday_positions"].items():
        ind = state.get("intraday_indicators", {}).get(sym)
        if ind:
            update_position_pnl(sym, ind["price"])

    state["dt_symbols"]  = tradeable
    state["dt_session"]  = get_session()

    logger.info(
        "SessionManager: day=%s  trades=%d  pnl=%.2f%%  positions=%d  tradeable=%d/%d",
        _session["date"],
        _session["trades_today"],
        _session["daily_pnl_pct"],
        len(_session["open_intraday_positions"]),
        len(tradeable), len(symbols),
    )
    return state
