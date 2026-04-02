"""ExecutionAgent — routes orders to Revolut X (crypto) or Alpaca (stocks/ETF).

Replaces the previous single-broker RevolutClient with an OrderRouter
that dispatches each signal to the correct exchange based on asset type.

No changes required in orchestrator.py — interface is identical.
"""

from __future__ import annotations

import logging

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

        result = _router.execute(signal, paper=paper)

        # Normalise result into Order TypedDict shape
        orders.append(
            Order(
                symbol=sym,
                action=action,
                amount_eur=amount,
                status=result.get("status", "unknown"),
                order_id=result.get("order_id", ""),
                broker=result.get("broker", "unknown"),
                error=result.get("error"),
            )
        )

    logger.info(
        "ExecutionAgent: %d orders — paper=%s", len(orders), paper
    )
    state["executed_orders"] = orders
    return state
