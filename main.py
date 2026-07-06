"""Investment Bot — entry point.

Usage:
  python main.py                                # paper mode, run once
  python main.py --loop                         # paper, every CYCLE_INTERVAL_MINUTES
  python main.py --mode live --confirm-live     # live (also needs LIVE_TRADING_CONFIRM=YES)

LIVE mode is gated by DOUBLE confirmation:
  1. CLI flag  --confirm-live
  2. env var   LIVE_TRADING_CONFIRM=YES
plus a capital hard-cap (LIVE_MAX_CAPITAL_EUR). Without both, the bot
falls back to paper mode and says so.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import schedule

from agents.orchestrator import run_cycle
from core import safety
from core.config import CYCLE_INTERVAL_MINUTES, LOG_LEVEL, TRADING_MODE
from core.db import init_db, load_latest_portfolio
from core.status_writer import write_status

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def _resolve_mode(args: argparse.Namespace) -> str:
    """Apply LIVE double-confirmation + hard-cap; fall back to paper."""
    if args.mode != "live":
        return "paper"

    snapshot = load_latest_portfolio()
    equity = snapshot["total_value_eur"] if snapshot else 0.0
    allowed, reason = safety.live_trading_allowed(equity, cli_confirm=args.confirm_live)
    if not allowed:
        logger.error("LIVE bloccato: %s — fallback a PAPER", reason)
        return "paper"

    logger.warning("=== MODALITÀ LIVE CONFERMATA (equity €%.2f) ===", equity)
    return "live"


def main() -> None:
    parser = argparse.ArgumentParser(description="Investment Bot")
    parser.add_argument("--mode", choices=["paper", "live"], default=TRADING_MODE)
    parser.add_argument("--confirm-live", action="store_true",
                        help="Prima conferma per LIVE (serve anche LIVE_TRADING_CONFIRM=YES)")
    parser.add_argument("--loop", action="store_true", help="Run continuously on schedule")
    args = parser.parse_args()

    init_db()
    logger.info("DB initialised")

    mode = _resolve_mode(args)
    logger.info("Starting bot in %s mode (selezione esplicita, loggata)", mode.upper())

    def job() -> None:
        # Kill-switch letto a ogni ciclo, PRIMA di fare qualsiasi cosa
        if safety.kill_switch_active():
            logger.warning("KILL-SWITCH attivo — ciclo saltato "
                           "(rimuovi con: python -m core.safety --resume)")
            return
        state = run_cycle(mode=mode)
        write_status(state)
        _print_summary(state)

    if not args.loop:
        job()
        return

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
    if safety.halt_active():
        print("⛔ HALT:    circuit-breaker attivo — sblocco: python -m core.safety --unlock")
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
