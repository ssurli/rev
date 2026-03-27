"""RiskManagerAgent — validates signals against risk rules.

Risk scoring formula (from revolut_invest_v3.html):
  +25  cash % < MIN_CASH_PCT (15%)
  +15  per position weight > MAX_POSITION_PCT (20%)
  +20  total crypto > MAX_CRYPTO_PCT (15%)
  +10  < 2 asset types
  cap at 100

Labels: Basso <30 | Medio 30-59 | Alto ≥60
"""

from __future__ import annotations

import logging

from core.config import (
    MAX_CRYPTO_PCT,
    MAX_POSITION_PCT,
    MAX_TRADE_EUR,
    MIN_CASH_PCT,
    MIN_PORTFOLIO_EUR,
    STOP_LOSS_PCT,
)
from core.state import BotState, PortfolioSnapshot, TradingSignal

logger = logging.getLogger(__name__)


def compute_risk_score(portfolio: PortfolioSnapshot) -> tuple[int, str]:
    """Compute 0-100 risk score and label."""
    positions = portfolio.get("positions", [])
    total = portfolio.get("total_value_eur", 0.0)
    cash = portfolio.get("cash_eur", 0.0)
    score = 0

    if total > 0:
        cash_pct = cash / total * 100.0
        if cash_pct < MIN_CASH_PCT:
            score += 25

        crypto_value = sum(
            p["value_eur"] for p in positions if p.get("asset_type") == "crypto"
        )
        if total and crypto_value / total * 100.0 > MAX_CRYPTO_PCT:
            score += 20

        for pos in positions:
            if total and pos.get("value_eur", 0) / total * 100.0 > MAX_POSITION_PCT:
                score += 15

        asset_types = {p.get("asset_type") for p in positions}
        if positions and len(asset_types) < 2:
            score += 10

    score = min(score, 100)
    label = "Basso" if score < 30 else ("Medio" if score < 60 else "Alto")
    return score, label


def _is_actionable(signal: TradingSignal) -> bool:
    return signal["action"] in ("BUY", "SELL", "TRIM")


def run(state: BotState) -> BotState:
    """Filter and validate signals; update portfolio risk score."""
    signals = state.get("signals", [])
    portfolio = state.get("portfolio", {})
    total_eur = portfolio.get("total_value_eur", 0.0)
    cash_eur = portfolio.get("cash_eur", 0.0)

    # Recompute risk score
    risk_score, risk_label = compute_risk_score(portfolio)
    portfolio["risk_score"] = risk_score
    portfolio["risk_label"] = risk_label
    state["portfolio"] = portfolio

    validated: list[TradingSignal] = []

    for signal in signals:
        action = signal["action"]
        sym = signal["symbol"]
        amount = signal["amount_eur"]

        # HOLD always passes through (no capital needed)
        if action == "HOLD":
            validated.append(signal)
            continue

        # Hard block: portfolio too small
        if total_eur < MIN_PORTFOLIO_EUR:
            logger.info("RiskManager: blocked %s %s — portfolio €%.2f < min €%.2f",
                        action, sym, total_eur, MIN_PORTFOLIO_EUR)
            state["errors"].append(f"Portfolio too small (€{total_eur:.2f}) — blocked {action} {sym}")
            continue

        # BUY checks
        if action == "BUY":
            # Not enough cash
            if cash_eur < amount:
                amount = cash_eur * 0.10  # reduce to 10% of available cash
                if amount < 5.0:
                    logger.info("RiskManager: blocked BUY %s — insufficient cash €%.2f", sym, cash_eur)
                    continue
                signal = dict(signal)  # type: ignore[assignment]
                signal["amount_eur"] = round(amount, 2)
                signal["reason"] += " [reduced to fit cash]"

            # Cap at MAX_TRADE_EUR
            if amount > MAX_TRADE_EUR:
                signal = dict(signal)  # type: ignore[assignment]
                signal["amount_eur"] = MAX_TRADE_EUR
                signal["reason"] += f" [capped at €{MAX_TRADE_EUR}]"

            # Risk score too high — block new BUYs
            if risk_score >= 60:
                logger.info("RiskManager: blocked BUY %s — risk=%d (Alto)", sym, risk_score)
                state["errors"].append(f"Risk Alto ({risk_score}) — blocked BUY {sym}")
                continue

        # SELL / TRIM checks
        if action in ("SELL", "TRIM"):
            if amount > MAX_TRADE_EUR:
                signal = dict(signal)  # type: ignore[assignment]
                signal["amount_eur"] = MAX_TRADE_EUR

        validated.append(signal)  # type: ignore[arg-type]

    actionable = sum(1 for s in validated if _is_actionable(s))
    logger.info("RiskManager: %d/%d signals validated (%d actionable) — risk=%d %s",
                len(validated), len(signals), actionable, risk_score, risk_label)

    state["validated_signals"] = validated
    return state
