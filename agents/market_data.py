"""MarketDataAgent — fetches real-time prices for all tracked assets.

Data sources (in order of preference):
1. yfinance  — ETF, stocks, commodities, crypto (Yahoo Finance)
2. Binance public REST  — crypto only, no key needed
3. CoinGecko — crypto fallback, no key needed
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests
import yfinance as yf

from core.config import ASSETS, EUR_USD_FALLBACK
from core.state import BotState, MarketData

logger = logging.getLogger(__name__)

# Classify assets
_CRYPTO = {"BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD"}
_COMMODITY = {"GLD", "SLV", "OIL", "GC=F", "CL=F"}

_BINANCE_MAP = {
    "BTC-USD": "BTCUSDT",
    "ETH-USD": "ETHUSDT",
    "BNB-USD": "BNBUSDT",
    "SOL-USD": "SOLUSDT",
    "XRP-USD": "XRPUSDT",
}

_COINGECKO_MAP = {
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
    "BNB-USD": "binancecoin",
    "SOL-USD": "solana",
    "XRP-USD": "ripple",
}


def _asset_type(symbol: str) -> str:
    if symbol in _CRYPTO:
        return "crypto"
    if symbol in _COMMODITY:
        return "commodity"
    if symbol.endswith("=X"):
        return "forex"
    if len(symbol) <= 4 and symbol.isupper():
        return "etf"
    return "stock"


def _fetch_eur_usd() -> float:
    try:
        ticker = yf.Ticker("EURUSD=X")
        hist = ticker.history(period="1d", interval="1m")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return EUR_USD_FALLBACK


def _usd_to_eur(price_usd: float, eur_usd: float) -> float:
    return price_usd / eur_usd if eur_usd else price_usd


def _fetch_yfinance(symbols: list[str], eur_usd: float) -> dict[str, MarketData]:
    result: dict[str, MarketData] = {}
    try:
        data = yf.download(
            symbols,
            period="2d",
            interval="1h",
            progress=False,
            auto_adjust=True,
        )
        if data.empty:
            return result

        # yfinance returns MultiIndex columns when multiple tickers
        close = data["Close"] if "Close" in data.columns else data.xs("Close", axis=1, level=0)
        volume = data["Volume"] if "Volume" in data.columns else data.xs("Volume", axis=1, level=0)

        for sym in symbols:
            try:
                col = sym if sym in close.columns else None
                if col is None:
                    continue
                series = close[col].dropna()
                if len(series) < 2:
                    continue
                current = float(series.iloc[-1])
                prev_24h = float(series.iloc[max(0, len(series) - 25)])
                prev_1h = float(series.iloc[-2]) if len(series) >= 2 else current
                change_pct = ((current - prev_24h) / prev_24h * 100) if prev_24h else 0.0
                vol_series = volume[col].dropna() if col in volume.columns else None
                vol = float(vol_series.iloc[-1]) if vol_series is not None and not vol_series.empty else 0.0

                # Convert to EUR if USD-denominated
                is_usd = sym.endswith("-USD") or sym.endswith("=F")
                price_eur = _usd_to_eur(current, eur_usd) if is_usd else current
                price_1h_eur = _usd_to_eur(prev_1h, eur_usd) if is_usd else prev_1h

                result[sym] = MarketData(
                    symbol=sym,
                    price_eur=round(price_eur, 4),
                    change_pct_24h=round(change_pct, 2),
                    volume=round(vol, 2),
                    price_1h_ago=round(price_1h_eur, 4),
                    asset_type=_asset_type(sym),
                )
            except Exception as exc:
                logger.debug("yfinance parse error for %s: %s", sym, exc)
    except Exception as exc:
        logger.warning("yfinance batch error: %s", exc)
    return result


def _fetch_binance(symbol: str, eur_usd: float) -> MarketData | None:
    binance_sym = _BINANCE_MAP.get(symbol)
    if not binance_sym:
        return None
    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbol": binance_sym},
            timeout=8,
        )
        resp.raise_for_status()
        d = resp.json()
        price_usd = float(d["lastPrice"])
        change_pct = float(d["priceChangePercent"])
        vol = float(d["volume"])
        price_eur = _usd_to_eur(price_usd, eur_usd)
        return MarketData(
            symbol=symbol,
            price_eur=round(price_eur, 4),
            change_pct_24h=round(change_pct, 2),
            volume=round(vol, 2),
            price_1h_ago=round(price_eur, 4),  # approximate
            asset_type="crypto",
        )
    except Exception as exc:
        logger.debug("Binance error for %s: %s", symbol, exc)
    return None


def run(state: BotState) -> BotState:
    """Fetch market data for all configured assets."""
    eur_usd = _fetch_eur_usd()
    state["eur_usd"] = eur_usd

    market: dict[str, MarketData] = {}

    # Try yfinance for everything
    yf_data = _fetch_yfinance(ASSETS, eur_usd)
    market.update(yf_data)

    # Fallback to Binance for crypto that yfinance missed
    for sym in ASSETS:
        if sym not in market and sym in _CRYPTO:
            result = _fetch_binance(sym, eur_usd)
            if result:
                market[sym] = result

    missing = [s for s in ASSETS if s not in market]
    if missing:
        logger.warning("MarketData: no data for %s", missing)
        state["errors"].append(f"MarketData: no data for {missing}")

    logger.info("MarketData: fetched %d/%d assets (EUR/USD=%.4f)", len(market), len(ASSETS), eur_usd)
    state["market_data"] = market
    return state
