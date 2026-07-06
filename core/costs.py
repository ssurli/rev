"""Cost gate — with 50–500 € the enemy #1 is fees and spread, not the strategy.

An order is blocked when the estimated total cost (taker fee + half the
bid/ask spread) exceeds COST_GATE_MAX_PCT of the order size, or when the
order is below the pair's minimum size.

Half-spread convention: a market order crosses the book and pays roughly
spread/2 versus mid price; the full spread is paid only on a round-trip.
"""

from __future__ import annotations

import logging

from core import config

logger = logging.getLogger(__name__)

# Per-pair minimum order size in EUR (fallback: config.MIN_ORDER_EUR).
# Update from the exchange's pair metadata when available.
MIN_ORDER_EUR_BY_SYMBOL: dict[str, float] = {
    "BTC-USD": 10.0,
    "ETH-USD": 10.0,
    "SOL-USD": 10.0,
}


def min_order_eur(symbol: str) -> float:
    return MIN_ORDER_EUR_BY_SYMBOL.get(symbol, config.MIN_ORDER_EUR)


def estimate_order_costs(
    amount_eur: float,
    spread_pct: float | None = None,
    fee_pct: float | None = None,
) -> dict:
    """Estimate execution costs for a market order of `amount_eur`.

    spread_pct is the full quoted spread in % (live value from the ticker
    when available, DEFAULT_SPREAD_PCT otherwise); we charge half of it.
    """
    fee_pct = config.TAKER_FEE_PCT if fee_pct is None else fee_pct
    spread_pct = config.DEFAULT_SPREAD_PCT if spread_pct is None else spread_pct

    fee_eur = amount_eur * fee_pct / 100.0
    spread_eur = amount_eur * (spread_pct / 2.0) / 100.0
    total_eur = fee_eur + spread_eur
    total_pct = (total_eur / amount_eur * 100.0) if amount_eur > 0 else 0.0

    return {
        "fee_eur": round(fee_eur, 4),
        "spread_eur": round(spread_eur, 4),
        "total_eur": round(total_eur, 4),
        "total_pct": round(total_pct, 4),
        "fee_pct": fee_pct,
        "spread_pct": spread_pct,
    }


def cost_gate(
    symbol: str,
    amount_eur: float,
    spread_pct: float | None = None,
    fee_pct: float | None = None,
    max_pct: float | None = None,
) -> tuple[bool, str, dict]:
    """Return (allowed, reason, cost_info) for a prospective order."""
    max_pct = config.COST_GATE_MAX_PCT if max_pct is None else max_pct

    if amount_eur <= 0:
        return False, "importo nullo o negativo", {}

    floor = min_order_eur(symbol)
    if amount_eur < floor:
        return False, f"sotto il min order size (€{amount_eur:.2f} < €{floor:.2f})", {}

    costs = estimate_order_costs(amount_eur, spread_pct=spread_pct, fee_pct=fee_pct)
    if costs["total_pct"] > max_pct:
        return (
            False,
            f"cost-gate: costi stimati {costs['total_pct']:.2f}% > {max_pct:.2f}% "
            f"(fee €{costs['fee_eur']:.2f} + ½spread €{costs['spread_eur']:.2f})",
            costs,
        )

    return True, "ok", costs
