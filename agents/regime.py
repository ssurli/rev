"""RegimeDetectorAgent — trend vs range filter per asset.

Classifica ogni asset in: trend_up | trend_down | range.
Metodo: distanza EMA20-EMA50 normalizzata per ATR(14).
  |EMA20 - EMA50| / ATR > 1.0  → trend (up se EMA20>EMA50)
  altrimenti                   → range

Uso a valle (strategy):
  - trend_down  → nessun nuovo BUY momentum
  - range       → soglia di score più alta (mean-reversion territory)
Fornisce anche atr_pct (ATR come % del prezzo) per sizing e stop.
"""

from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf

from core.config import ASSETS, ENABLE_REGIME_FILTER
from core.state import BotState

logger = logging.getLogger(__name__)

_TREND_STRENGTH_MIN = 1.0  # |EMA20-EMA50| in ATR units


def atr_series(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def classify_regime(high: pd.Series, low: pd.Series, close: pd.Series) -> dict:
    """Pure function — classify regime from OHLC series (testable offline)."""
    if len(close) < 60:
        return {"regime": "range", "atr_pct": 0.0, "trend_strength": 0.0}

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    atr = atr_series(high, low, close)

    last_atr = float(atr.iloc[-1])
    last_close = float(close.iloc[-1])
    if last_atr <= 0 or last_close <= 0:
        return {"regime": "range", "atr_pct": 0.0, "trend_strength": 0.0}

    gap = float(ema20.iloc[-1] - ema50.iloc[-1])
    strength = abs(gap) / last_atr
    atr_pct = last_atr / last_close * 100.0

    if strength > _TREND_STRENGTH_MIN:
        regime = "trend_up" if gap > 0 else "trend_down"
    else:
        regime = "range"

    return {
        "regime": regime,
        "atr_pct": round(atr_pct, 3),
        "trend_strength": round(strength, 3),
    }


def run(state: BotState) -> BotState:
    regimes: dict[str, dict] = {}
    if not ENABLE_REGIME_FILTER:
        state["regimes"] = regimes
        return state

    for sym in ASSETS:
        try:
            hist = yf.Ticker(sym).history(period="6mo", interval="1d")
            if hist.empty or len(hist) < 60:
                continue
            regimes[sym] = classify_regime(hist["High"], hist["Low"], hist["Close"])
        except Exception as exc:
            logger.warning("Regime error for %s: %s", sym, exc)

    counts = {}
    for r in regimes.values():
        counts[r["regime"]] = counts.get(r["regime"], 0) + 1
    logger.info("RegimeAgent: %d assets — %s", len(regimes), counts)

    state["regimes"] = regimes
    return state
