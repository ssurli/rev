"""TechnicalAnalysisAgent — calcola indicatori tecnici per ogni asset.

Indicatori calcolati (con pandas, nessuna dipendenza extra):
- RSI(14): >70 overbought, <30 oversold
- MA20 / MA50: golden cross (MA20>MA50) / death cross
- MACD(12,26,9): crossover linea segnale
- Bollinger Bands(20,2): posizione del prezzo nella banda
- Momentum 5 giorni: variazione % su 5 periodi

tech_score [-1,+1]: media pesata degli indicatori
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import yfinance as yf

from core.config import ASSETS
from core.state import BotState, TechnicalIndicators

logger = logging.getLogger(__name__)


def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    val = rsi_series.iloc[-1]
    return float(val) if not np.isnan(val) else 50.0


def _macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float, float]:
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(hist.iloc[-1])


def _bollinger(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> tuple[float, float, float]:
    ma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = ma + std_dev * std
    lower = ma - std_dev * std
    price = series.iloc[-1]
    u, l = float(upper.iloc[-1]), float(lower.iloc[-1])
    if u == l:
        position = 0.5
    else:
        position = (price - l) / (u - l)
        position = max(0.0, min(1.0, position))
    return u, l, position


def _tech_score(rsi: float, ma_cross: str, macd_hist: float, bb_position: float, momentum_5d: float) -> float:
    """Weighted composite score [-1, +1]."""
    # RSI: 30=+1 (oversold=bullish), 70=-1 (overbought=bearish)
    rsi_score = (50 - rsi) / 50.0
    rsi_score = max(-1.0, min(1.0, rsi_score))

    # MA cross
    ma_score = 0.6 if ma_cross == "golden" else (-0.6 if ma_cross == "death" else 0.0)

    # MACD histogram: positive = bullish
    macd_score = np.tanh(macd_hist * 10)

    # Bollinger: <0.2 = near lower band = bullish, >0.8 = near upper = bearish
    bb_score = (0.5 - bb_position) * 2.0
    bb_score = max(-1.0, min(1.0, bb_score))

    # Momentum 5d
    mom_score = np.tanh(momentum_5d / 5.0)

    score = (
        rsi_score   * 0.25 +
        ma_score    * 0.30 +
        macd_score  * 0.20 +
        bb_score    * 0.15 +
        mom_score   * 0.10
    )
    return round(float(score), 3)


def _compute(symbol: str) -> TechnicalIndicators | None:
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="3mo", interval="1d")
        if hist.empty or len(hist) < 30:
            logger.warning("Technical: not enough data for %s (%d rows)", symbol, len(hist))
            return None

        close = hist["Close"]

        rsi = _rsi(close)
        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else ma20
        ma_cross = "golden" if ma20 > ma50 else ("death" if ma20 < ma50 else "neutral")
        macd, macd_sig, macd_hist = _macd(close)
        bb_upper, bb_lower, bb_pos = _bollinger(close)
        momentum_5d = float((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100) if len(close) >= 6 else 0.0

        score = _tech_score(rsi, ma_cross, macd_hist, bb_pos, momentum_5d)

        return TechnicalIndicators(
            symbol=symbol,
            rsi=round(rsi, 1),
            ma20=round(ma20, 4),
            ma50=round(ma50, 4),
            ma_cross=ma_cross,
            macd=round(macd, 4),
            macd_signal=round(macd_sig, 4),
            macd_hist=round(macd_hist, 4),
            bb_upper=round(bb_upper, 4),
            bb_lower=round(bb_lower, 4),
            bb_position=round(bb_pos, 3),
            momentum_5d=round(momentum_5d, 2),
            tech_score=score,
        )
    except Exception as exc:
        logger.warning("Technical error for %s: %s", symbol, exc)
        return None


def run(state: BotState) -> BotState:
    """Compute technical indicators for all assets."""
    indicators: dict[str, TechnicalIndicators] = {}
    for sym in ASSETS:
        result = _compute(sym)
        if result:
            indicators[sym] = result
            logger.debug("Technical %s: RSI=%.1f MA=%s score=%.2f",
                         sym, result["rsi"], result["ma_cross"], result["tech_score"])

    logger.info("TechnicalAgent: computed %d/%d assets", len(indicators), len(ASSETS))
    state["technical_indicators"] = indicators
    return state
