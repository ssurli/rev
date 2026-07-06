"""Backtest metrics — pure functions on the equity curve and trade list."""

from __future__ import annotations

import math


def sharpe_ratio(equity: list[float], periods_per_year: int = 365) -> float:
    """Annualised Sharpe (rf=0) from a per-period equity curve."""
    if len(equity) < 3:
        return 0.0
    returns = [
        equity[i] / equity[i - 1] - 1.0
        for i in range(1, len(equity)) if equity[i - 1] > 0
    ]
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / len(returns)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return round(mean / std * math.sqrt(periods_per_year), 3)


def max_drawdown_pct(equity: list[float]) -> float:
    """Max peak-to-trough drawdown in % (positive number)."""
    peak = -float("inf")
    max_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak * 100.0)
    return round(max_dd, 2)


def hit_rate(trades: list[dict]) -> float:
    """Fraction of closed trades with positive net PnL."""
    closed = [t for t in trades if "pnl_eur" in t]
    if not closed:
        return 0.0
    wins = sum(1 for t in closed if t["pnl_eur"] > 0)
    return round(wins / len(closed), 3)


def profit_factor(trades: list[dict]) -> float:
    gross_win = sum(t["pnl_eur"] for t in trades if t.get("pnl_eur", 0) > 0)
    gross_loss = -sum(t["pnl_eur"] for t in trades if t.get("pnl_eur", 0) < 0)
    if gross_loss == 0:
        return float("inf") if gross_win > 0 else 0.0
    return round(gross_win / gross_loss, 3)


def total_costs_eur(trades: list[dict]) -> float:
    return round(sum(t.get("costs_eur", 0.0) for t in trades), 2)


def summary(equity: list[float], trades: list[dict], periods_per_year: int = 365) -> dict:
    closed = [t for t in trades if "pnl_eur" in t]
    start = equity[0] if equity else 0.0
    end = equity[-1] if equity else 0.0
    return {
        "start_equity_eur": round(start, 2),
        "end_equity_eur": round(end, 2),
        "total_return_pct": round((end / start - 1) * 100.0, 2) if start > 0 else 0.0,
        "sharpe": sharpe_ratio(equity, periods_per_year),
        "max_drawdown_pct": max_drawdown_pct(equity),
        "n_trades": len(closed),
        "hit_rate": hit_rate(trades),
        "profit_factor": profit_factor(trades),
        "total_costs_eur": total_costs_eur(trades),
    }
