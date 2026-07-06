"""ExecutionAgent — routes orders to Revolut X (crypto) or Alpaca (stocks/ETF).

Replaces the previous single-broker RevolutClient with an OrderRouter
that dispatches each signal to the correct exchange based on asset type.

No changes required in orchestrator.py — interface is identical.
"""

from __future__ import annotations

import logging

from core import notifier
from core.config import TAKER_FEE_PCT
from core.ledger import record_fill
from core.order_router import OrderRouter
from core.state import BotState, Order

logger = logging.getLogger(__name__)

# Module-level singleton — created once per process
_router = OrderRouter()


def run(state: BotState) -> BotState:
    """Execute all validated actionable signals."""
    mode = state.get("mode", "paper")
    paper = mode != "live"

    validated = state.get("validated_signals", [])
    eur_usd = state.get("eur_usd", 1.08) or 1.08
    orders: list[Order] = []

    for signal in validated:
        action = signal["action"]
        if action not in ("BUY", "SELL", "TRIM"):
            continue  # HOLD — nothing to execute

        sym = signal["symbol"]
        amount = signal["amount_eur"]
        confidence = signal["confidence"]

        logger.info(
            "Execution: %s %s €%.2f (conf=%.2f reason=%r)",
            action, sym, amount, confidence, signal["reason"][:60],
        )

        try:
            result = _router.execute(signal, paper=paper)
        except Exception as exc:
            logger.error("Execution failed for %s %s: %s", action, sym, exc)
            state["errors"].append(f"execution {sym}: {exc}")
            if not paper:
                notifier.notify_error(f"Ordine {action} {sym}", str(exc))
            continue

        # Normalise result into Order TypedDict shape
        orders.append(
            Order(
                symbol=sym,
                action=action,
                amount_eur=amount,
                price_eur=signal.get("price_eur", 0.0),
                status=result.get("status", "unknown"),
                mode=mode,
                order_id=result.get("order_id", ""),
                broker=result.get("broker", "unknown"),
                error=result.get("error"),
            )
        )

        # --- v2: tax ledger + alerts on executed fills ---
        if result.get("status") in ("filled", "simulated"):
            price_eur = signal.get("price_eur", 0.0)
            qty = result.get("qty") or (amount / price_eur if price_eur > 0 else 0.0)
            fee_eur = result.get("fee") or amount * TAKER_FEE_PCT / 100.0
            side = "BUY" if action == "BUY" else "SELL"
            try:
                record_fill(
                    order_id=result.get("order_id", ""),
                    cycle_id=state.get("cycle_id", ""),
                    symbol=sym,
                    side=side,
                    qty=qty,
                    price=price_eur * eur_usd,   # quote-ccy (USD) price
                    price_ccy="USD",
                    eur_rate=1.0 / eur_usd,
                    fee_eur=float(fee_eur),
                    broker=result.get("broker", "unknown"),
                    mode=mode,
                )
            except Exception as exc:
                logger.error("Ledger record_fill failed for %s: %s", sym, exc)
                state["errors"].append(f"ledger {sym}: {exc}")

            if not paper:
                notifier.notify_order({**result, "amount_eur": amount})
                if "Stop-loss" in signal.get("reason", ""):
                    notifier.notify_stop_hit(sym, signal["reason"])

    logger.info(
        "ExecutionAgent: %d orders — paper=%s", len(orders), paper
    )
    state["executed_orders"] = orders
    return state
