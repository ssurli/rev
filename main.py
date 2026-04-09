"""Investment Bot — entry point.

Usage:
  python main.py                          # paper mode, swing cycle once
  python main.py --mode live              # live mode, swing cycle once
  python main.py --loop                   # swing cycle every 60 min
  python main.py --loop --intraday        # swing (60 min) + day-trading (5 min)
  python main.py --mode live --loop --intraday
  python main.py --intraday-only          # only day-trading cycle (no swing)

Day trading is also toggled by setting "enabled": true in config.json → day_trading,
or by passing DAY_TRADING_ENABLED=true in .env.
"""

from __future__ import annotations

import argparse
import logging
import time

import schedule

from agents.orchestrator import run_cycle
from core.config import (
    CYCLE_INTERVAL_MINUTES,
    DAY_TRADING_ENABLED,
    INTRADAY_CYCLE_MINUTES,
    LOG_LEVEL,
    TRADING_MODE,
)
from core.db import init_db

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

# Shared reference to last swing portfolio snapshot (passed to intraday cycle)
_last_portfolio: dict = {}


# ---------------------------------------------------------------------------
# Swing cycle
# ---------------------------------------------------------------------------

def _run_swing(mode: str) -> None:
    global _last_portfolio
    state = run_cycle(mode=mode)
    _print_summary(state)
    if state.get("portfolio"):
        _last_portfolio = state["portfolio"]


# ---------------------------------------------------------------------------
# Intraday cycle
# ---------------------------------------------------------------------------

def _run_intraday(mode: str) -> None:
    """Execute one intraday (5-min) day-trading cycle."""
    # Lazy import to avoid circular deps when day trading not used
    from agents.intraday_orchestrator import run_intraday_cycle
    run_intraday_cycle(mode=mode, portfolio=_last_portfolio)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Investment Bot")
    parser.add_argument("--mode",          choices=["paper", "live"], default=TRADING_MODE)
    parser.add_argument("--loop",          action="store_true",
                        help="Run swing cycle continuously on schedule")
    parser.add_argument("--intraday",      action="store_true",
                        help="Also run day-trading cycle every INTRADAY_CYCLE_MINUTES min")
    parser.add_argument("--intraday-only", action="store_true",
                        help="Run only the day-trading cycle (no swing cycle)")
    args = parser.parse_args()

    # env/flag resolution for day trading
    use_intraday = args.intraday or args.intraday_only or DAY_TRADING_ENABLED

    init_db()
    logger.info("DB initialised")
    logger.info("Starting bot — mode=%s  swing=%s  intraday=%s",
                args.mode.upper(),
                "off" if args.intraday_only else f"every {CYCLE_INTERVAL_MINUTES}m",
                f"every {INTRADAY_CYCLE_MINUTES}m" if use_intraday else "off")

    # ── Single run ───────────────────────────────────────────────────────
    if not args.loop and not args.intraday_only:
        state = run_cycle(mode=args.mode)
        _print_summary(state)
        if use_intraday:
            _last_portfolio.update(state.get("portfolio", {}))
            _run_intraday(args.mode)
        return

    if args.intraday_only and not args.loop:
        _run_intraday(args.mode)
        return

    # ── Scheduled loop ───────────────────────────────────────────────────
    if not args.intraday_only:
        schedule.every(CYCLE_INTERVAL_MINUTES).minutes.do(_run_swing, mode=args.mode)
        logger.info("Scheduler: swing cycle every %d min", CYCLE_INTERVAL_MINUTES)
        _run_swing(args.mode)  # run immediately on start

    if use_intraday:
        schedule.every(INTRADAY_CYCLE_MINUTES).minutes.do(_run_intraday, mode=args.mode)
        logger.info("Scheduler: intraday cycle every %d min", INTRADAY_CYCLE_MINUTES)
        if args.intraday_only:
            _run_intraday(args.mode)  # run immediately when swing skipped

    while True:
        schedule.run_pending()
        time.sleep(10)


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def _print_summary(state: dict) -> None:
    portfolio = state.get("portfolio", {})
    orders    = state.get("executed_orders", [])
    errors    = state.get("errors", [])

    print("\n" + "=" * 60)
    print(f"SWING  {state.get('cycle_id')}  {state.get('timestamp', '')[:19]}")
    print(f"Mode     : {state.get('mode', '').upper()}")
    print(f"Portfolio: €{portfolio.get('total_value_eur', 0):.2f} total  |  "
          f"€{portfolio.get('cash_eur', 0):.2f} cash")
    print(f"Risk     : {portfolio.get('risk_score', 0)}/100 ({portfolio.get('risk_label', '-')})")
    print(f"News     : {len(state.get('news_items', []))} items processed")

    signals   = state.get("validated_signals", [])
    actionable = [s for s in signals if s["action"] in ("BUY", "SELL", "TRIM")]
    if actionable:
        print(f"Signals  : {len(actionable)} actionable")
        for s in actionable:
            print(f"  {s['action']:5s} {s['symbol']:10s} €{s['amount_eur']:.2f}  "
                  f"conf={s['confidence']:.2f}  {s['reason'][:50]}")
    else:
        print("Signals  : no actionable signals this cycle")

    if orders:
        print(f"Orders   : {len(orders)} placed")
        for o in orders:
            print(f"  [{o['status'].upper():12s}] {o['action']} {o['symbol']} "
                  f"€{o['amount_eur']:.2f}")

    if errors:
        print(f"Errors   : {len(errors)}")
        for e in errors:
            print(f"  ! {e}")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
