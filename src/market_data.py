"""
market_data.py
Dati di mercato in tempo reale tramite Yahoo Finance (yfinance).
Copre: azioni, ETF, crypto, commodity.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


class MarketDataClient:
    """Wrapper Yahoo Finance per dati di mercato."""

    def __init__(self, config_path: str = "config.json"):
        with open(config_path) as f:
            self.config = json.load(f)

    # ─── Quotazione singolo asset ─────────────────────────────────────────────

    def get_quote(self, symbol: str) -> dict:
        """Quotazione real-time per un singolo asset."""
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info

        try:
            current_price = info.last_price
            prev_close = info.previous_close
            change_pct = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0.0
            volume = info.three_month_average_volume or 0

            return {
                "symbol": symbol,
                "price": round(current_price, 4),
                "prev_close": round(prev_close, 4),
                "change_pct": round(change_pct, 2),
                "volume": int(volume),
                "currency": info.currency or "USD",
                "market_cap": info.market_cap,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"symbol": symbol, "error": str(e)}

    def get_quotes(self, symbols: list[str]) -> dict[str, dict]:
        """Quotazioni per lista di asset (batch, più veloce)."""
        results = {}
        tickers = yf.Tickers(" ".join(symbols))
        for sym in symbols:
            try:
                t = tickers.tickers[sym]
                info = t.fast_info
                prev_close = info.previous_close or 0
                price = info.last_price or 0
                change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0
                results[sym] = {
                    "symbol": sym,
                    "price": round(price, 4),
                    "change_pct": round(change_pct, 2),
                    "currency": info.currency or "USD",
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                results[sym] = {"symbol": sym, "error": str(e)}
        return results

    # ─── Dati storici ─────────────────────────────────────────────────────────

    def get_history(self, symbol: str, days: int = 90) -> pd.DataFrame:
        """Dati storici OHLCV per N giorni."""
        ticker = yf.Ticker(symbol)
        end = datetime.now()
        start = end - timedelta(days=days)
        df = ticker.history(start=start, end=end)
        return df

    def get_weekly_change(self, symbol: str) -> float:
        """Variazione percentuale nell'ultima settimana."""
        df = self.get_history(symbol, days=10)
        if len(df) < 2:
            return 0.0
        return round((df["Close"].iloc[-1] / df["Close"].iloc[-6] - 1) * 100, 2)

    def get_monthly_change(self, symbol: str) -> float:
        """Variazione percentuale nell'ultimo mese."""
        df = self.get_history(symbol, days=35)
        if len(df) < 2:
            return 0.0
        return round((df["Close"].iloc[-1] / df["Close"].iloc[0] - 1) * 100, 2)

    def get_52w_range(self, symbol: str) -> dict:
        """Minimo e massimo a 52 settimane."""
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return {
            "low_52w": info.get("fiftyTwoWeekLow"),
            "high_52w": info.get("fiftyTwoWeekHigh"),
        }

    # ─── Indicatori tecnici ───────────────────────────────────────────────────

    def calc_rsi(self, symbol: str, period: int = 14) -> float:
        """RSI (Relative Strength Index) su N periodi."""
        df = self.get_history(symbol, days=period * 3)
        if df.empty or len(df) < period:
            return 50.0  # neutro se dati insufficienti

        delta = df["Close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=period).mean().iloc[-1]
        avg_loss = loss.rolling(window=period).mean().iloc[-1]

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    def calc_sma(self, symbol: str, period: int = 20) -> float:
        """Media mobile semplice su N giorni."""
        df = self.get_history(symbol, days=period + 5)
        if df.empty or len(df) < period:
            return 0.0
        return round(df["Close"].rolling(window=period).mean().iloc[-1], 4)

    def calc_volume_ratio(self, symbol: str) -> float:
        """Rapporto volume attuale vs media 20gg (>2 = anomalo)."""
        df = self.get_history(symbol, days=30)
        if df.empty or len(df) < 5:
            return 1.0
        avg_vol = df["Volume"].rolling(20).mean().iloc[-1]
        last_vol = df["Volume"].iloc[-1]
        return round(last_vol / avg_vol, 2) if avg_vol > 0 else 1.0

    # ─── Analisi completa asset ───────────────────────────────────────────────

    def full_analysis(self, symbol: str) -> dict:
        """
        Analisi completa di un asset:
        quotazione + variazioni + indicatori tecnici + range 52w.
        """
        quote = self.get_quote(symbol)
        if "error" in quote:
            return quote

        rsi = self.calc_rsi(symbol)
        sma20 = self.calc_sma(symbol, 20)
        sma50 = self.calc_sma(symbol, 50)
        vol_ratio = self.calc_volume_ratio(symbol)
        week_chg = self.get_weekly_change(symbol)
        month_chg = self.get_monthly_change(symbol)
        range_52w = self.get_52w_range(symbol)

        # Segnale tecnico base
        signal = "HOLD"
        if rsi < self.config["alerts"]["rsi_oversold"] and quote["price"] > sma50 * 0.98:
            signal = "BUY"
        elif rsi > self.config["alerts"]["rsi_overbought"] and quote["price"] > sma20 * 1.05:
            signal = "SELL/TRIM"

        return {
            **quote,
            "week_change_pct": week_chg,
            "month_change_pct": month_chg,
            "rsi_14": rsi,
            "sma_20": sma20,
            "sma_50": sma50,
            "volume_ratio": vol_ratio,
            "range_52w_low": range_52w["low_52w"],
            "range_52w_high": range_52w["high_52w"],
            "technical_signal": signal,
            "volume_alert": vol_ratio >= self.config["alerts"]["volume_anomaly_multiplier"],
        }

    # ─── Watchlist ────────────────────────────────────────────────────────────

    def scan_watchlist(self, watchlist_path: str = "watchlist.json") -> list[dict]:
        """
        Scansiona tutta la watchlist e ritorna i dati di mercato.
        Segnala automaticamente alert su variazioni anomale.
        """
        with open(watchlist_path) as f:
            watchlist = json.load(f)

        all_symbols = (
            watchlist.get("stocks", [])
            + watchlist.get("etf", [])
            + watchlist.get("crypto", [])
            + watchlist.get("commodities", [])
        )

        results = []
        threshold = self.config["alerts"]["daily_change_threshold_pct"]

        for sym in all_symbols:
            data = self.full_analysis(sym)
            data["alert"] = abs(data.get("change_pct", 0)) >= threshold
            results.append(data)

        return sorted(results, key=lambda x: abs(x.get("change_pct", 0)), reverse=True)
