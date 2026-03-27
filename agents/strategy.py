"""StrategyAgent — generates BUY/SELL/TRIM/HOLD signals.

Rules (adapted from revolut_invest_v3.html):
- BUY   if sentiment > +0.40 AND price hasn't already risen > 3% in last hour
- SELL  if sentiment < -0.40 OR position P&L ≤ -15% (stop-loss)
- TRIM  if position weight > 20% of portfolio OR P&L ≥ +30% (take-profit)
- HOLD  otherwise

For borderline confidence (0.30 – 0.60), Claude is asked for a final call.
"""

from __future__ import annotations

import json
import logging

import anthropic

from core.config import (
    ANTHROPIC_API_KEY,
    ASSETS,
    CLAUDE_MODEL,
    MAX_POSITION_PCT,
    MAX_TRADE_EUR,
    MIN_CASH_PCT,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
)
from core.state import BotState, PortfolioSnapshot, TradingSignal

logger = logging.getLogger(__name__)

_SENTIMENT_BUY_THRESHOLD = 0.40
_SENTIMENT_SELL_THRESHOLD = -0.40
_PRICE_SURGE_GUARD = 3.0   # don't buy if already up >3% in last hour
_BORDERLINE_LOW = 0.30
_BORDERLINE_HIGH = 0.60


def _position_pnl(sym: str, portfolio: PortfolioSnapshot) -> float | None:
    for pos in portfolio.get("positions", []):
        if pos["symbol"] == sym:
            return pos.get("pnl_pct", 0.0)
    return None


def _position_weight(sym: str, portfolio: PortfolioSnapshot) -> float:
    total = portfolio.get("total_value_eur", 0.0)
    if total <= 0:
        return 0.0
    for pos in portfolio.get("positions", []):
        if pos["symbol"] == sym:
            return pos.get("value_eur", 0.0) / total * 100.0
    return 0.0


def _ask_claude(signals_borderline: list[dict], portfolio: PortfolioSnapshot) -> dict[str, str]:
    """Ask Claude for a final BUY/SELL/HOLD decision on borderline signals.
    Returns {symbol: action} mapping."""
    if not ANTHROPIC_API_KEY or not signals_borderline:
        return {}

    context = json.dumps(
        {
            "portfolio_summary": {
                "total_eur": portfolio.get("total_value_eur"),
                "cash_eur": portfolio.get("cash_eur"),
                "risk_score": portfolio.get("risk_score"),
            },
            "borderline_signals": signals_borderline,
        },
        indent=2,
    )
    prompt = (
        "You are a conservative investment bot managing a small retail portfolio.\n"
        "Review these borderline signals and decide BUY, SELL, or HOLD for each.\n"
        "Respond ONLY with a JSON object: {\"SYMBOL\": \"BUY\"|\"SELL\"|\"HOLD\"}.\n\n"
        f"{context}"
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Strategy Claude call failed: %s", exc)
        return {}


def run(state: BotState) -> BotState:
    """Generate trading signals from sentiment + market data + portfolio state."""
    sentiment = state.get("sentiment_scores", {})
    market = state.get("market_data", {})
    portfolio = state.get("portfolio", {})
    total_eur = portfolio.get("total_value_eur", 0.0)
    cash_eur = portfolio.get("cash_eur", 0.0)

    signals: list[TradingSignal] = []
    borderline: list[dict] = []

    for sym in ASSETS:
        score = sentiment.get(sym, 0.0)
        md = market.get(sym)
        if md is None:
            continue

        price = md["price_eur"]
        change_1h = (price - md["price_1h_ago"]) / md["price_1h_ago"] * 100.0 if md["price_1h_ago"] else 0.0
        pnl = _position_pnl(sym, portfolio)
        weight = _position_weight(sym, portfolio)

        # Stop-loss override
        if pnl is not None and pnl <= STOP_LOSS_PCT:
            signals.append(TradingSignal(
                symbol=sym, action="SELL", confidence=1.0,
                amount_eur=min(MAX_TRADE_EUR, portfolio.get("total_value_eur", 50) * 0.05),
                reason=f"Stop-loss triggered: P&L={pnl:.1f}%",
                sentiment_score=score, price_eur=price,
            ))
            continue

        # Take-profit / overweight trim
        if pnl is not None and (pnl >= TAKE_PROFIT_PCT or weight > MAX_POSITION_PCT):
            reason = (
                f"Take-profit at P&L={pnl:.1f}%" if pnl >= TAKE_PROFIT_PCT
                else f"Position overweight: {weight:.1f}% > {MAX_POSITION_PCT}%"
            )
            signals.append(TradingSignal(
                symbol=sym, action="TRIM", confidence=0.85,
                amount_eur=min(MAX_TRADE_EUR, total_eur * 0.03),
                reason=reason, sentiment_score=score, price_eur=price,
            ))
            continue

        # Sentiment-driven signals
        confidence = min(abs(score) + abs(change_1h) / 10.0, 1.0)

        if score >= _SENTIMENT_BUY_THRESHOLD:
            if change_1h > _PRICE_SURGE_GUARD:
                # Price already surged — don't chase
                continue
            if cash_eur / total_eur * 100.0 < MIN_CASH_PCT:
                signals.append(TradingSignal(
                    symbol=sym, action="HOLD", confidence=0.5,
                    amount_eur=0.0,
                    reason=f"BUY skipped: cash below {MIN_CASH_PCT}%",
                    sentiment_score=score, price_eur=price,
                ))
                continue
            amount = min(MAX_TRADE_EUR, cash_eur * 0.10)
            if _BORDERLINE_LOW <= confidence <= _BORDERLINE_HIGH:
                borderline.append({"symbol": sym, "score": score, "change_1h": change_1h, "confidence": confidence})
            else:
                signals.append(TradingSignal(
                    symbol=sym, action="BUY", confidence=round(confidence, 2),
                    amount_eur=round(amount, 2),
                    reason=f"Positive sentiment={score:.2f}, 1h_change={change_1h:.2f}%",
                    sentiment_score=score, price_eur=price,
                ))

        elif score <= _SENTIMENT_SELL_THRESHOLD:
            if pnl is None:
                # Not in position — skip
                continue
            if _BORDERLINE_LOW <= confidence <= _BORDERLINE_HIGH:
                borderline.append({"symbol": sym, "score": score, "change_1h": change_1h, "confidence": confidence})
            else:
                signals.append(TradingSignal(
                    symbol=sym, action="SELL", confidence=round(confidence, 2),
                    amount_eur=min(MAX_TRADE_EUR, total_eur * 0.05),
                    reason=f"Negative sentiment={score:.2f}",
                    sentiment_score=score, price_eur=price,
                ))
        else:
            signals.append(TradingSignal(
                symbol=sym, action="HOLD", confidence=round(confidence, 2),
                amount_eur=0.0,
                reason=f"Neutral sentiment={score:.2f}",
                sentiment_score=score, price_eur=price,
            ))

    # Claude assist for borderline signals
    if borderline:
        claude_decisions = _ask_claude(borderline, portfolio)
        for b in borderline:
            sym = b["symbol"]
            action = claude_decisions.get(sym, "HOLD")
            md = market.get(sym)
            price = md["price_eur"] if md else 0.0
            signals.append(TradingSignal(
                symbol=sym, action=action, confidence=b["confidence"],
                amount_eur=min(MAX_TRADE_EUR, cash_eur * 0.08) if action == "BUY" else min(MAX_TRADE_EUR, total_eur * 0.04),
                reason=f"Claude borderline decision (sentiment={b['score']:.2f})",
                sentiment_score=b["score"], price_eur=price,
            ))

    logger.info("StrategyAgent: %d signals (%d BUY, %d SELL, %d TRIM, %d HOLD)",
                len(signals),
                sum(1 for s in signals if s["action"] == "BUY"),
                sum(1 for s in signals if s["action"] == "SELL"),
                sum(1 for s in signals if s["action"] == "TRIM"),
                sum(1 for s in signals if s["action"] == "HOLD"))

    state["signals"] = signals
    return state
