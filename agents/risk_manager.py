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

from core import safety
from core.config import (
    MAX_CRYPTO_PCT,
    MAX_DAILY_TURNOVER_PCT,
    MAX_POSITION_PCT,
    MAX_TRADE_EUR,
    MAX_TRADES_PER_DAY,
    MIN_CASH_PCT,
    MIN_PORTFOLIO_EUR,
    STOP_LOSS_PCT,
    TRADE_COOLDOWN_MINUTES,
)
from core.costs import cost_gate
from core.db import count_trades_today, minutes_since_last_trade, turnover_today_eur
from core.decision_log import log_decision
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

    mode = state.get("mode", "paper")
    cycle_id = state.get("cycle_id", "")

    # Recompute risk score
    risk_score, risk_label = compute_risk_score(portfolio)
    portfolio["risk_score"] = risk_score
    portfolio["risk_label"] = risk_label
    state["portfolio"] = portfolio

    # --- v2 global gates: kill-switch, drawdown circuit-breaker -----------
    if safety.kill_switch_active():
        logger.warning("RiskManager: KILL-SWITCH attivo — nessun ordine")
        log_decision(cycle_id, "*", "*", "halted", "kill-switch attivo")
        state["validated_signals"] = [s for s in signals if s["action"] == "HOLD"]
        return state

    halted, drawdown_pct = safety.check_drawdown(total_eur)
    if halted:
        info = safety.halt_info() or {}
        logger.warning("RiskManager: HALT attivo (drawdown %.1f%%) — nessun ordine", drawdown_pct)
        log_decision(cycle_id, "*", "*", "halted",
                     f"circuit-breaker: {info.get('reason', 'halt attivo')}")
        state["validated_signals"] = [s for s in signals if s["action"] == "HOLD"]
        return state

    # --- v2 daily counters (anti-overtrading) -----------------------------
    trades_today = count_trades_today(mode)
    turnover_today = turnover_today_eur(mode)
    max_turnover_eur = total_eur * MAX_DAILY_TURNOVER_PCT / 100.0

    validated: list[TradingSignal] = []

    def _reject(sig: TradingSignal, reason: str) -> None:
        logger.info("RiskManager: blocked %s %s — %s", sig["action"], sig["symbol"], reason)
        log_decision(cycle_id, sig["symbol"], sig["action"], "rejected", reason,
                     {"amount_eur": sig["amount_eur"], "confidence": sig["confidence"]})

    for signal in signals:
        action = signal["action"]
        sym = signal["symbol"]
        amount = signal["amount_eur"]

        # HOLD always passes through (no capital needed)
        if action == "HOLD":
            validated.append(signal)
            continue

        # --- v2: overtrading guards ---
        if trades_today + sum(1 for s in validated if _is_actionable(s)) >= MAX_TRADES_PER_DAY:
            _reject(signal, f"max {MAX_TRADES_PER_DAY} trade/giorno raggiunto")
            continue

        mins = minutes_since_last_trade(sym, mode)
        if mins is not None and mins < TRADE_COOLDOWN_MINUTES:
            _reject(signal, f"cooldown: ultimo trade su {sym} {mins:.0f}min fa "
                            f"(min {TRADE_COOLDOWN_MINUTES}min)")
            continue

        pending_turnover = sum(s["amount_eur"] for s in validated if _is_actionable(s))
        if turnover_today + pending_turnover + amount > max_turnover_eur > 0:
            _reject(signal, f"turnover giornaliero: €{turnover_today + pending_turnover + amount:.2f} "
                            f"> €{max_turnover_eur:.2f} ({MAX_DAILY_TURNOVER_PCT}% equity)")
            continue

        # --- v2: cost gate (fee + spread vs order size) ---
        allowed, gate_reason, gate_costs = cost_gate(sym, amount)
        if not allowed:
            _reject(signal, gate_reason)
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

        log_decision(cycle_id, sym, action, "accepted", signal["reason"],
                     {"amount_eur": signal["amount_eur"], "confidence": signal["confidence"],
                      "cost_gate": gate_costs})
        validated.append(signal)  # type: ignore[arg-type]

    actionable = sum(1 for s in validated if _is_actionable(s))
    logger.info("RiskManager: %d/%d signals validated (%d actionable) — risk=%d %s",
                len(validated), len(signals), actionable, risk_score, risk_label)

    state["validated_signals"] = validated
    return state
