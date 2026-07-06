"""Regime detector — trend vs range on synthetic series."""

import numpy as np
import pandas as pd

from agents.regime import classify_regime


def _ohlc(prices: np.ndarray) -> tuple[pd.Series, pd.Series, pd.Series]:
    close = pd.Series(prices)
    high = close * 1.005
    low = close * 0.995
    return high, low, close


def test_uptrend_detected():
    prices = np.linspace(100, 200, 120)  # steady climb
    high, low, close = _ohlc(prices)
    res = classify_regime(high, low, close)
    assert res["regime"] == "trend_up"
    assert res["trend_strength"] > 1.0
    assert res["atr_pct"] > 0


def test_downtrend_detected():
    prices = np.linspace(200, 100, 120)
    high, low, close = _ohlc(prices)
    res = classify_regime(high, low, close)
    assert res["regime"] == "trend_down"


def test_range_detected():
    rng = np.random.default_rng(42)
    prices = 100 + 3 * np.sin(np.linspace(0, 12 * np.pi, 120)) + rng.normal(0, 0.5, 120)
    high, low, close = _ohlc(prices)
    res = classify_regime(high, low, close)
    assert res["regime"] == "range"


def test_short_series_defaults_to_range():
    prices = np.linspace(100, 120, 30)  # < 60 bars
    high, low, close = _ohlc(prices)
    res = classify_regime(high, low, close)
    assert res["regime"] == "range"
    assert res["atr_pct"] == 0.0
