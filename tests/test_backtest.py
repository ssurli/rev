"""Backtest metrics + engine on synthetic data (no network)."""

import numpy as np
import pandas as pd

from backtest.engine import Backtester
from backtest.metrics import (
    hit_rate,
    max_drawdown_pct,
    profit_factor,
    sharpe_ratio,
    summary,
    total_costs_eur,
)


def test_max_drawdown():
    equity = [100, 120, 90, 110, 80, 130]
    # peak 120 → trough 80 = 33.33%
    assert abs(max_drawdown_pct(equity) - 33.33) < 0.01


def test_sharpe_sign():
    up = [100 * (1.001 ** i) for i in range(200)]
    down = [100 * (0.999 ** i) for i in range(200)]
    assert sharpe_ratio(up) > 0
    assert sharpe_ratio(down) < 0


def test_hit_rate_and_profit_factor():
    trades = [
        {"pnl_eur": 10.0, "costs_eur": 0.5},
        {"pnl_eur": -5.0, "costs_eur": 0.5},
        {"pnl_eur": 20.0, "costs_eur": 0.5},
        {"pnl_eur": -10.0, "costs_eur": 0.5},
    ]
    assert hit_rate(trades) == 0.5
    assert profit_factor(trades) == 2.0     # 30 / 15
    assert total_costs_eur(trades) == 2.0


def test_summary_keys():
    s = summary([100, 110, 105], [{"pnl_eur": 5.0, "costs_eur": 0.2}])
    for key in ("sharpe", "max_drawdown_pct", "hit_rate", "profit_factor",
                "total_costs_eur", "n_trades", "total_return_pct"):
        assert key in s


def _synthetic_ohlc(n=400, seed=7) -> pd.DataFrame:
    """Downtrend then strong uptrend → forces an EMA cross entry."""
    rng = np.random.default_rng(seed)
    down = np.linspace(120, 100, 150)
    up = np.linspace(100, 180, n - 150)
    close = np.concatenate([down, up]) + rng.normal(0, 0.4, n)
    return pd.DataFrame({
        "Open": close,
        "High": close * 1.01,
        "Low": close * 0.99,
        "Close": close,
    })


def test_engine_runs_and_costs_accounted():
    bt = Backtester("BTC-USD", _synthetic_ohlc(), start_equity_eur=500.0)
    result = bt.run()
    report = result["report"]

    assert len(result["equity_curve"]) > 0
    assert report["n_trades"] >= 1, "the EMA cross on synthetic uptrend must trade"
    # every trade carries execution costs
    for t in result["trades"]:
        assert t["costs_eur"] > 0
    assert report["total_costs_eur"] > 0
    # equity accounting sane: end equity == start + sum(pnl)
    total_pnl = sum(t["pnl_eur"] for t in result["trades"])
    assert abs(report["end_equity_eur"] - (500.0 + total_pnl)) < 1.0


def test_engine_no_trades_on_flat_expensive_market():
    """With a prohibitive cost gate no order should ever pass."""
    bt = Backtester("BTC-USD", _synthetic_ohlc(), start_equity_eur=500.0,
                    spread_pct=5.0)  # ½spread 2.5% >> gate 0.4%
    result = bt.run()
    assert result["report"]["n_trades"] == 0
    assert result["report"]["end_equity_eur"] == 500.0
