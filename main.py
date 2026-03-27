"""Investment Bot — entry point.

Usage:
  python main.py                  # paper mode, run once
  python main.py --mode live      # live mode, run once
  python main.py --loop           # run every CYCLE_INTERVAL_MINUTES minutes
  python main.py --mode live --loop
"""

from __future__ import annotations

import argparse
import logging
import time

import schedule

from agents.orchestrator import run_cycle
from core.config import CYCLE_INTERVAL_MINUTES, LOG_LEVEL, TRADING_MODE
from core.db import init_db

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def main() -> None:
    parser = argparse.ArgumentParser(description="Investment Bot")
    parser.add_argument("--mode", choices=["paper", "live"], default=TRADING_MODE)
    parser.add_argument("--loop", action="store_true", help="Run continuously on schedule")
    args = parser.parse_args()

    # Init database
    init_db()
    logger.info("DB initialised")
    logger.info("Starting bot in %s mode", args.mode.upper())

    if not args.loop:
        state = run_cycle(mode=args.mode)
        _print_summary(state)
        return

    # Scheduled loop
    def job():
        state = run_cycle(mode=args.mode)
        _print_summary(state)

    schedule.every(CYCLE_INTERVAL_MINUTES).minutes.do(job)
    logger.info("Scheduler: running every %d minutes", CYCLE_INTERVAL_MINUTES)
    job()  # run immediately on start

    while True:
        schedule.run_pending()
        time.sleep(10)


def _print_summary(state: dict) -> None:
    portfolio = state.get("portfolio", {})
    orders = state.get("executed_orders", [])
    errors = state.get("errors", [])

    print("\n" + "=" * 60)
    print(f"CYCLE {state.get('cycle_id')} — {state.get('timestamp', '')[:19]}")
    print(f"Mode:      {state.get('mode', '').upper()}")
    print(f"Portfolio: €{portfolio.get('total_value_eur', 0):.2f} total | "
          f"€{portfolio.get('cash_eur', 0):.2f} cash")
    print(f"Risk:      {portfolio.get('risk_score', 0)}/100 ({portfolio.get('risk_label', '-')})")
    print(f"News:      {len(state.get('news_items', []))} items processed")

    signals = state.get("validated_signals", [])
    actionable = [s for s in signals if s["action"] in ("BUY", "SELL", "TRIM")]
    if actionable:
        print(f"Signals:   {len(actionable)} actionable")
        for s in actionable:
            print(f"  {s['action']:5s} {s['symbol']:10s} €{s['amount_eur']:.2f}  "
                  f"conf={s['confidence']:.2f}  {s['reason'][:50]}")
    else:
        print("Signals:   no actionable signals this cycle")

    if orders:
        print(f"Orders:    {len(orders)} placed")
        for o in orders:
            print(f"  [{o['status'].upper():12s}] {o['action']} {o['symbol']} €{o['amount_eur']:.2f}")

    if errors:
        print(f"Errors:    {len(errors)}")
        for e in errors:
            print(f"  ! {e}")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
