"""IntradayOrchestrator — lightweight 5-minute day trading cycle.

Pipeline (no LangGraph overhead — simple sequential calls):
  session_manager → intraday_data → intraday_signals → intraday_strategy → execution

Runs in parallel to the main swing cycle (60 min).
Portfolio state is passed in from the last swing cycle snapshot.

Usage (from main.py):
    from agents.intraday_orchestrator import run_intraday_cycle
    state = run_intraday_cycle(mode="paper", portfolio=last_swing_state["portfolio"])
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agents import intraday_data, intraday_signals, intraday_strategy, session_manager
from core.config import ASSETS, TRADING_MODE
from core.order_router import OrderRouter

logger = logging.getLogger(__name__)

_CFG_PATH = Path(__file__).parent.parent / "config.json"

# Singleton router — created once per process, shared with swing cycle
_router = OrderRouter()


def _load_dt_config() -> dict:
    try:
        with open(_CFG_PATH) as f:
            return json.load(f).get("day_trading", {})
    except Exception:
        return {}


def _print_intraday_summary(state: dict) -> None:
    orders  = state.get("intraday_orders", [])
    session = state.get("dt_session", {})
    errors  = state.get("errors", [])

    print(f"\n{'─'*55}")
    print(f"INTRADAY  {state.get('cycle_id')}  {state.get('timestamp','')[:19]}")
    print(f"  Day P&L : {session.get('daily_pnl_pct',0):+.2f}%  "
          f"(€{session.get('daily_pnl_eur',0):+.2f})")
    print(f"  Trades  : {session.get('trades_today',0)}  |  "
          f"Open positions: {len(session.get('open_intraday_positions',{}))}")

    if orders:
        for o in orders:
            tag = "✓" if o["status"] in ("filled", "paper_filled") else "✗"
            print(f"  {tag} {o['action']:5s} {o['symbol']:10s} €{o['amount_eur']:.2f}  "
                  f"@ {o['price_eur']:.4f}  [{o['trigger']}]  {o['status']}")
    else:
        print("  No intraday orders this cycle")

    if errors:
        for e in errors:
            print(f"  ! {e}")
    print(f"{'─'*55}\n")


def run_intraday_cycle(
    mode:      str        = TRADING_MODE,
    portfolio: dict | None = None,
) -> dict:
    """Execute one intraday (5-min) cycle.

    Args:
        mode:      "paper" or "live"
        portfolio: latest portfolio snapshot from the swing orchestrator

    Returns:
        state dict with intraday_signals, intraday_orders, errors, dt_session
    """
    dt_cfg = _load_dt_config()

    if not dt_cfg.get("enabled", False):
        logger.debug("IntradayOrchestrator: day trading disabled — skipping")
        return {"intraday_signals": [], "intraday_orders": [], "errors": []}

    cycle_id = f"DT-{str(uuid.uuid4())[:6]}"
    paper    = mode != "live"

    # Symbols for day trading: use dedicated list from config if set, else ASSETS
    dt_symbols: list[str] = dt_cfg.get("symbols", []) or ASSETS

    state: dict = {
        "cycle_id":            cycle_id,
        "mode":                mode,
        "dt_symbols":          list(dt_symbols),
        "portfolio":           portfolio or {},
        "intraday_candles":    {},
        "intraday_indicators": {},
        "intraday_signals":    [],
        "intraday_orders":     [],
        "dt_session":          {},
        "errors":              [],
        "timestamp":           datetime.now(timezone.utc).isoformat(),
    }

    logger.info("=== INTRADAY CYCLE %s START [%s] ===", cycle_id, mode.upper())

    # ── Step 1: Session check (market hours + circuit breakers) ──────────
    try:
        state = session_manager.run(state)
    except Exception as exc:
        logger.error("SessionManager error: %s", exc)
        state["errors"].append(f"session_manager: {exc}")

    if not state["dt_symbols"]:
        logger.info("IntradayCycle %s: no tradeable symbols (market closed)", cycle_id)
        return state

    # ── Step 2: Fetch intraday candles ───────────────────────────────────
    try:
        state = intraday_data.run(state)
    except Exception as exc:
        logger.error("IntradayData error: %s", exc)
        state["errors"].append(f"intraday_data: {exc}")

    if not state.get("intraday_candles"):
        logger.warning("IntradayCycle %s: no candle data — aborting", cycle_id)
        return state

    # ── Step 3: Compute indicators ───────────────────────────────────────
    try:
        state = intraday_signals.run(state)
    except Exception as exc:
        logger.error("IntradaySignals error: %s", exc)
        state["errors"].append(f"intraday_signals: {exc}")

    # ── Step 4: Generate signals ─────────────────────────────────────────
    try:
        state = intraday_strategy.run(state)
    except Exception as exc:
        logger.error("IntradayStrategy error: %s", exc)
        state["errors"].append(f"intraday_strategy: {exc}")

    # ── Step 5: Execute signals ──────────────────────────────────────────
    cooldown_min = dt_cfg.get("cooldown_after_stop_minutes", 30)
    orders: list[dict] = []

    for signal in state.get("intraday_signals", []):
        action     = signal["action"]
        sym        = signal["symbol"]
        amount_eur = signal["amount_eur"]
        price      = signal["price_eur"]
        trigger    = signal.get("trigger", "")

        try:
            result = _router.execute(signal, paper=paper)
            status = result.get("status", "unknown")

            orders.append({
                "cycle_id":      cycle_id,
                "symbol":        sym,
                "action":        action,
                "amount_eur":    amount_eur,
                "price_eur":     price,
                "stop_loss":     signal.get("stop_loss"),
                "take_profit":   signal.get("take_profit"),
                "status":        status,
                "broker":        result.get("broker", "unknown"),
                "trigger":       trigger,
                "intraday_score":signal.get("intraday_score", 0.0),
                "reason":        signal.get("reason", "")[:120],
                "error":         result.get("error"),
                "timestamp":     datetime.now(timezone.utc).isoformat(),
            })

            if status in ("filled", "paper_filled"):
                session_manager.register_order(
                    symbol      = sym,
                    action      = action,
                    amount_eur  = amount_eur,
                    price       = price,
                    stop_loss   = signal.get("stop_loss", price * 0.985),
                    take_profit = signal.get("take_profit", price * 1.025),
                )
                if trigger == "stop_loss":
                    session_manager.add_cooldown(sym, cooldown_min)

        except Exception as exc:
            logger.error("IntradayExecution %s %s: %s", action, sym, exc)
            state["errors"].append(f"execution_{sym}: {exc}")

    state["intraday_orders"] = orders
    # Refresh session snapshot after order registration
    state["dt_session"] = session_manager.get_session()

    buy_n  = sum(1 for o in orders if o["action"] == "BUY")
    sell_n = sum(1 for o in orders if o["action"] in ("SELL", "TRIM"))
    logger.info(
        "=== INTRADAY CYCLE %s END — BUY=%d SELL/TRIM=%d orders=%d errors=%d ===",
        cycle_id, buy_n, sell_n, len(orders), len(state["errors"]),
    )

    _print_intraday_summary(state)
    return state
