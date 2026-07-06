"""Position sizing — risk-based, ATR-driven, confidence-scaled, fractional.

Rule: the amount is derived from how much you are willing to LOSE if the
stop is hit (RISK_PER_TRADE_PCT of equity), not from how much cash is
available. Caps: MAX_TRADE_EUR, MAX_CASH_PER_TRADE_PCT of cash, and the
pair's minimum order size (below the minimum → no trade).
"""

from __future__ import annotations

import logging

from core import config
from core.costs import min_order_eur

logger = logging.getLogger(__name__)


def position_size(
    symbol: str,
    equity_eur: float,
    cash_eur: float,
    price_eur: float,
    confidence: float,
    atr_pct: float | None = None,
) -> dict:
    """Compute order size, stop-loss and take-profit for a BUY.

    atr_pct: ATR(14) as % of price (currency-independent). Fallback:
    |STOP_LOSS_PCT| as stop distance when no ATR is available.

    Returns dict with amount_eur (0 = no trade + reason), qty,
    stop_loss_eur, take_profit_eur, risk_eur.
    """
    result = {
        "amount_eur": 0.0, "qty": 0.0,
        "stop_loss_eur": 0.0, "take_profit_eur": 0.0,
        "risk_eur": 0.0, "reason": "",
    }

    if price_eur <= 0 or equity_eur <= 0:
        result["reason"] = "prezzo o equity non validi"
        return result

    # Stop distance as % of price
    if atr_pct and atr_pct > 0:
        stop_pct = atr_pct * config.ATR_STOP_MULT
        tp_pct = atr_pct * config.ATR_TP_MULT
    else:
        stop_pct = abs(config.STOP_LOSS_PCT)
        tp_pct = config.TAKE_PROFIT_PCT

    # Max loss allowed at stop
    max_risk_eur = equity_eur * config.RISK_PER_TRADE_PCT / 100.0

    # amount * stop_pct% = max_risk  →  amount = max_risk / stop_pct%
    amount = max_risk_eur / (stop_pct / 100.0)

    # Scale with signal confidence (0..1)
    confidence = max(0.0, min(1.0, confidence))
    amount *= confidence

    # Hard caps
    amount = min(
        amount,
        config.MAX_TRADE_EUR,
        cash_eur * config.MAX_CASH_PER_TRADE_PCT / 100.0,
        cash_eur,  # can't spend more than we have
    )

    floor = min_order_eur(symbol)
    if amount < floor:
        result["reason"] = (
            f"size €{amount:.2f} sotto il minimo €{floor:.2f} "
            f"(risk {config.RISK_PER_TRADE_PCT}% × conf {confidence:.2f})"
        )
        return result

    qty = round(amount / price_eur, 8)  # fractional qty
    stop_loss = price_eur * (1 - stop_pct / 100.0)
    take_profit = price_eur * (1 + tp_pct / 100.0)
    risk_eur = amount * stop_pct / 100.0

    result.update({
        "amount_eur": round(amount, 2),
        "qty": qty,
        "stop_loss_eur": round(stop_loss, 6),
        "take_profit_eur": round(take_profit, 6),
        "risk_eur": round(risk_eur, 2),
        "reason": "ok",
    })
    return result
