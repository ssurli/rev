"""IntradayDataAgent — fetches multi-timeframe candles for day trading.

Timeframes fetched per asset:
  - 5m  (primary: signal generation)
  - 15m (confirmation: trend filter)
  - 1h  (context: macro trend)

Sources:
  - Binance public REST  (crypto — no key, faster, no rate limit issues)
  - yfinance             (stocks/ETF/commodities — fallback for crypto too)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import requests
import yfinance as yf

from core.config import ASSETS

logger = logging.getLogger(__name__)

_CRYPTO_SYMBOLS: frozenset[str] = frozenset({
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD",
    "ADA-USD", "DOGE-USD", "AVAX-USD", "DOT-USD", "MATIC-USD",
    "LINK-USD", "LTC-USD", "UNI-USD", "ATOM-USD", "NEAR-USD",
})

_BINANCE_MAP: dict[str, str] = {
    "BTC-USD":   "BTCUSDT",
    "ETH-USD":   "ETHUSDT",
    "BNB-USD":   "BNBUSDT",
    "SOL-USD":   "SOLUSDT",
    "XRP-USD":   "XRPUSDT",
    "ADA-USD":   "ADAUSDT",
    "DOGE-USD":  "DOGEUSDT",
    "AVAX-USD":  "AVAXUSDT",
    "DOT-USD":   "DOTUSDT",
    "LINK-USD":  "LINKUSDT",
    "LTC-USD":   "LTCUSDT",
    "UNI-USD":   "UNIUSDT",
    "ATOM-USD":  "ATOMUSDT",
    "NEAR-USD":  "NEARUSDT",
}

# yfinance interval → (period, limit_rows)
_YF_PARAMS: dict[str, tuple[str, int]] = {
    "5m":  ("1d",  100),
    "15m": ("5d",  100),
    "1h":  ("5d",  80),
}

# Binance interval → kline limit
_BINANCE_LIMIT: dict[str, int] = {
    "5m":  100,
    "15m": 100,
    "1h":  80,
}


# ---------------------------------------------------------------------------
# Binance
# ---------------------------------------------------------------------------

def _fetch_binance(symbol: str, interval: str) -> pd.DataFrame:
    binance_sym = _BINANCE_MAP.get(symbol)
    if not binance_sym:
        return pd.DataFrame()
    limit = _BINANCE_LIMIT.get(interval, 100)
    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": binance_sym, "interval": interval, "limit": limit},
            timeout=8,
        )
        resp.raise_for_status()
        raw = resp.json()
        df = pd.DataFrame(raw, columns=[
            "open_time", "Open", "High", "Low", "Close", "Volume",
            "close_time", "quote_vol", "trades", "taker_base", "taker_quote", "ignore",
        ])
        for col in ("Open", "High", "Low", "Close", "Volume"):
            df[col] = df[col].astype(float)
        df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        return df[["Open", "High", "Low", "Close", "Volume"]]
    except Exception as exc:
        logger.debug("Binance klines error %s %s: %s", symbol, interval, exc)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# yfinance
# ---------------------------------------------------------------------------

def _fetch_yfinance(symbol: str, interval: str) -> pd.DataFrame:
    period, _ = _YF_PARAMS.get(interval, ("1d", 100))
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index, utc=True)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        return df
    except Exception as exc:
        logger.debug("yfinance candles error %s %s: %s", symbol, interval, exc)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_candles(symbol: str, interval: str = "5m") -> pd.DataFrame:
    """Fetch OHLCV candles for a symbol and timeframe.

    Tries Binance first for crypto (faster, no rate limits),
    falls back to yfinance for everything.
    """
    if symbol in _CRYPTO_SYMBOLS:
        df = _fetch_binance(symbol, interval)
        if not df.empty and len(df) >= 20:
            return df

    return _fetch_yfinance(symbol, interval)


def fetch_multi_timeframe(symbol: str) -> dict[str, pd.DataFrame]:
    """Return candles on 3 timeframes: 5m, 15m, 1h."""
    return {
        "5m":  fetch_candles(symbol, "5m"),
        "15m": fetch_candles(symbol, "15m"),
        "1h":  fetch_candles(symbol, "1h"),
    }


def run(state: dict) -> dict:
    """Fetch intraday candles for all day-trading symbols."""
    symbols: list[str] = state.get("dt_symbols", ASSETS)
    candles: dict[str, dict[str, pd.DataFrame]] = {}

    for sym in symbols:
        mtf = fetch_multi_timeframe(sym)
        has_data = any(not df.empty for df in mtf.values())
        if has_data:
            candles[sym] = mtf
            logger.debug(
                "IntradayData %s: 5m=%d  15m=%d  1h=%d rows",
                sym, len(mtf["5m"]), len(mtf["15m"]), len(mtf["1h"]),
            )
        else:
            logger.warning("IntradayData: no candle data for %s", sym)

    logger.info("IntradayData: fetched %d/%d assets", len(candles), len(symbols))
    state["intraday_candles"] = candles
    state["intraday_timestamp"] = datetime.now(timezone.utc).isoformat()
    return state
