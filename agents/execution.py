"""ExecutionAgent — places orders via Revolut API (or simulates in paper mode)."""

from __future__ import annotations

import logging

from core.revolut_client import RevolutClient
from core.state import BotState, Order, TradingSignal

logger = logging.getLogger(__name__)

_client = RevolutClient()
_authenticated = False


def _ensure_auth() -> bool:
    global _authenticated
    if not _authenticated:
        _authenticated = _client.authenticate()
    return _authenticated


def run(state: BotState) -> BotState:
    """Execute all validated actionable signals."""
    if not _ensure_auth():
        state["errors"].append("Revolut auth failed — skipping execution")
        state["executed_orders"] = []
        return state

    validated = state.get("validated_signals", [])
    orders: list[Order] = []

    for signal in validated:
        action = signal["action"]
        if action not in ("BUY", "SELL", "TRIM"):
            continue  # HOLD signals need no execution

        sym = signal["symbol"]
        amount = signal["amount_eur"]
        price = signal["price_eur"]
        confidence = signal["confidence"]

        logger.info(
            "Execution: %s %s €%.2f (confidence=%.2f reason=%r)",
            action, sym, amount, confidence, signal["reason"][:60],
        )

        result = _client.place_order(
            symbol=sym,
            action=action if action != "TRIM" else "SELL",
            amount_eur=amount,
            price_eur=price,
        )
        orders.append(Order(**result))  # type: ignore[misc]

    logger.info("ExecutionAgent: placed %d orders", len(orders))
    state["executed_orders"] = orders
    return state
