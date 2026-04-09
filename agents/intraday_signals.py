"""IntradaySignalsAgent — computes intraday technical indicators on 5m candles.

Indicators per asset:
  - EMA 9 / EMA 21      fast trend crossover (primary signal)
  - VWAP                volume-weighted average price (intraday equilibrium)
  - RSI(5)              fast momentum oscillator
  - ATR(14)             volatility → dynamic stop-loss / take-profit sizing
  - Stochastic(5,3,3)   %K/%D momentum confirmation

Composite intraday_score [-1, +1]:
  EMA position (0.30) + VWAP side (0.25) + RSI (0.20) + Stochastic (0.15) + 1h trend (0.10)
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_MIN_ROWS_5M = 22   # minimum candles required to compute all indicators


# ---------------------------------------------------------------------------
# Pure indicator functions
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 5) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    val = (100 - (100 / (1 + rs))).iloc[-1]
    return float(val) if not np.isnan(val) else 50.0


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    """Average True Range — used for dynamic stop/take sizing."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    # Fallback: 1% of price if ATR not computable
    return float(val) if not np.isnan(val) else float(close.iloc[-1]) * 0.01


def _vwap(df: pd.DataFrame) -> float:
    """VWAP from available candles (no intraday reset needed — we only have 1d data)."""
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    vol = df["Volume"].replace(0, np.nan)
    vwap_val = (typical * vol).cumsum() / vol.cumsum()
    val = vwap_val.iloc[-1]
    return float(val) if not np.isnan(val) else float(df["Close"].iloc[-1])


def _stochastic(df: pd.DataFrame, k_period: int = 5, d_period: int = 3) -> tuple[float, float]:
    """Stochastic oscillator — returns (%K smoothed, %D)."""
    low_min  = df["Low"].rolling(k_period).min()
    high_max = df["High"].rolling(k_period).max()
    denom    = (high_max - low_min).replace(0, np.nan)
    raw_k    = 100 * (df["Close"] - low_min) / denom
    k_smooth = raw_k.rolling(d_period).mean()
    d        = k_smooth.rolling(d_period).mean()
    k_val, d_val = k_smooth.iloc[-1], d.iloc[-1]
    return (
        float(k_val) if not np.isnan(k_val) else 50.0,
        float(d_val) if not np.isnan(d_val) else 50.0,
    )


# ---------------------------------------------------------------------------
# Per-symbol computation
# ---------------------------------------------------------------------------

def _compute(symbol: str,
             df_5m: pd.DataFrame,
             df_15m: pd.DataFrame,
             df_1h: pd.DataFrame) -> dict | None:
    """Compute all intraday indicators. Returns None if data insufficient."""
    if df_5m.empty or len(df_5m) < _MIN_ROWS_5M:
        logger.debug("IntradaySignals %s: insufficient 5m rows (%d)", symbol, len(df_5m))
        return None

    close = df_5m["Close"]
    price = float(close.iloc[-1])

    # --- EMA 9 / EMA 21 ---
    ema9_s  = _ema(close, 9)
    ema21_s = _ema(close, 21)
    ema9    = float(ema9_s.iloc[-1])
    ema21   = float(ema21_s.iloc[-1])
    ema9_p  = float(ema9_s.iloc[-2])  if len(ema9_s)  >= 2 else ema9
    ema21_p = float(ema21_s.iloc[-2]) if len(ema21_s) >= 2 else ema21

    # Crossover state: fresh cross wins, otherwise positional
    if ema9_p <= ema21_p and ema9 > ema21:
        ema_cross = "bullish_cross"
    elif ema9_p >= ema21_p and ema9 < ema21:
        ema_cross = "bearish_cross"
    elif ema9 > ema21:
        ema_cross = "above"
    else:
        ema_cross = "below"

    # --- VWAP ---
    vwap = _vwap(df_5m)
    price_vs_vwap_pct = (price - vwap) / vwap * 100

    # --- RSI(5) ---
    rsi5 = _rsi(close, 5)

    # --- ATR(14) ---
    atr = _atr(df_5m, 14)

    # --- Stochastic(5,3,3) ---
    stoch_k, stoch_d = _stochastic(df_5m, 5, 3)
    stoch_prev_k = float(_ema(close, 5).iloc[-2]) if len(close) >= 2 else stoch_k  # rough proxy
    stoch_cross = (
        "bullish_cross" if stoch_k > stoch_d and stoch_k < 80 else
        "bearish_cross" if stoch_k < stoch_d and stoch_k > 20 else
        "above" if stoch_k > stoch_d else "below"
    )

    # --- 1h trend filter ---
    trend_1h = "bullish"
    if not df_1h.empty and len(df_1h) >= 10:
        c1h = df_1h["Close"]
        trend_1h = "bullish" if float(_ema(c1h, 9).iloc[-1]) > float(_ema(c1h, 21).iloc[-1]) else "bearish"

    # --- 15m momentum ---
    momentum_15m = 0.0
    if not df_15m.empty and len(df_15m) >= 5:
        c15 = df_15m["Close"]
        momentum_15m = float((c15.iloc[-1] - c15.iloc[-5]) / c15.iloc[-5] * 100)

    # --- Composite intraday_score [-1, +1] ---
    ema_score   = 0.6  if ema9 > ema21 else -0.6
    vwap_score  = 0.4  if price > vwap  else -0.4
    rsi_score   = max(-1.0, min(1.0, (50 - rsi5) / 50.0))
    stoch_score = 0.3  if stoch_k > stoch_d else -0.3
    trend_score = 0.3  if trend_1h == "bullish" else -0.3

    intraday_score = round(
        ema_score   * 0.30 +
        vwap_score  * 0.25 +
        rsi_score   * 0.20 +
        stoch_score * 0.15 +
        trend_score * 0.10,
        3,
    )

    return {
        "symbol":          symbol,
        "price":           round(price, 4),
        "ema9":            round(ema9, 4),
        "ema21":           round(ema21, 4),
        "ema_cross":       ema_cross,
        "vwap":            round(vwap, 4),
        "price_vs_vwap":   round(price_vs_vwap_pct, 2),
        "rsi5":            round(rsi5, 1),
        "atr":             round(atr, 6),
        "stoch_k":         round(stoch_k, 1),
        "stoch_d":         round(stoch_d, 1),
        "stoch_cross":     stoch_cross,
        "trend_1h":        trend_1h,
        "momentum_15m":    round(momentum_15m, 2),
        "intraday_score":  intraday_score,
    }


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

def run(state: dict) -> dict:
    """Compute intraday indicators for all assets that have candle data."""
    candles: dict[str, dict] = state.get("intraday_candles", {})
    indicators: dict[str, dict] = {}

    for sym, mtf in candles.items():
        result = _compute(
            sym,
            mtf.get("5m",  pd.DataFrame()),
            mtf.get("15m", pd.DataFrame()),
            mtf.get("1h",  pd.DataFrame()),
        )
        if result:
            indicators[sym] = result
            logger.debug(
                "IntradaySignals %s: score=%+.2f  EMA=%s  RSI5=%.1f  VWAP%+.2f%%  ATR=%.4f",
                sym, result["intraday_score"], result["ema_cross"],
                result["rsi5"], result["price_vs_vwap"], result["atr"],
            )

    logger.info("IntradaySignals: computed %d/%d assets", len(indicators), len(candles))
    state["intraday_indicators"] = indicators
    return state
