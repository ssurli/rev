"""Backtester offline su candele storiche — obbligatorio prima del go-live.

Simula la stessa logica del bot live in forma semplificata ma con gli
stessi vincoli economici dei piccoli capitali:
  - segnale: EMA20/EMA50 con filtro regime (trend vs range);
  - sizing risk-based (RISK_PER_TRADE_PCT, ATR stop);
  - costi realistici su ogni fill: taker fee + metà spread;
  - cost gate e min order size identici al live;
  - stop-loss / take-profit valutati intrabar su high/low.

Output: equity curve + trade list + report metriche
(Sharpe, max drawdown, hit rate, profit factor, costi totali).
"""

from __future__ import annotations

import logging

import pandas as pd

from agents.regime import atr_series, classify_regime
from backtest.metrics import summary
from core import config
from core.costs import cost_gate, estimate_order_costs
from core.sizing import position_size

logger = logging.getLogger(__name__)


class Backtester:
    def __init__(
        self,
        symbol: str,
        ohlc: pd.DataFrame,          # columns: Open, High, Low, Close
        start_equity_eur: float = 200.0,
        fee_pct: float | None = None,
        spread_pct: float | None = None,
    ) -> None:
        self.symbol = symbol
        self.ohlc = ohlc
        self.start_equity = start_equity_eur
        self.fee_pct = config.TAKER_FEE_PCT if fee_pct is None else fee_pct
        self.spread_pct = config.DEFAULT_SPREAD_PCT if spread_pct is None else spread_pct

    # ------------------------------------------------------------------

    def run(self) -> dict:
        cash = self.start_equity
        position: dict | None = None   # {qty, entry, stop, tp, costs}
        equity_curve: list[float] = []
        trades: list[dict] = []

        close = self.ohlc["Close"]
        high = self.ohlc["High"]
        low = self.ohlc["Low"]
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        atr = atr_series(high, low, close)

        for i in range(60, len(close)):
            price = float(close.iloc[i])
            bar_high = float(high.iloc[i])
            bar_low = float(low.iloc[i])

            # --- exits first: TPSL intrabar ---
            if position is not None:
                exit_price = None
                exit_reason = None
                if bar_low <= position["stop"]:
                    exit_price, exit_reason = position["stop"], "stop_loss"
                elif bar_high >= position["tp"]:
                    exit_price, exit_reason = position["tp"], "take_profit"
                elif float(ema20.iloc[i]) < float(ema50.iloc[i]):
                    exit_price, exit_reason = price, "signal_exit"

                if exit_price is not None:
                    gross = position["qty"] * exit_price
                    costs = estimate_order_costs(gross, self.spread_pct, self.fee_pct)["total_eur"]
                    cash += gross - costs
                    total_costs = position["costs"] + costs
                    trades.append({
                        "side": "LONG",
                        "entry": position["entry"],
                        "exit": exit_price,
                        "qty": position["qty"],
                        "reason": exit_reason,
                        "costs_eur": round(total_costs, 4),
                        "pnl_eur": round(
                            position["qty"] * (exit_price - position["entry"]) - total_costs, 4),
                    })
                    position = None

            # --- entries ---
            if position is None:
                window_hi = high.iloc[: i + 1]
                window_lo = low.iloc[: i + 1]
                window_cl = close.iloc[: i + 1]
                reg = classify_regime(window_hi, window_lo, window_cl)

                bullish = float(ema20.iloc[i]) > float(ema50.iloc[i])
                crossed_up = bullish and float(ema20.iloc[i - 1]) <= float(ema50.iloc[i - 1])

                if crossed_up and reg["regime"] != "trend_down":
                    equity = cash
                    size = position_size(
                        symbol=self.symbol, equity_eur=equity, cash_eur=cash,
                        price_eur=price, confidence=0.7, atr_pct=reg["atr_pct"],
                    )
                    if size["amount_eur"] > 0:
                        allowed, _, _ = cost_gate(
                            self.symbol, size["amount_eur"],
                            spread_pct=self.spread_pct, fee_pct=self.fee_pct,
                        )
                        if allowed:
                            costs = estimate_order_costs(
                                size["amount_eur"], self.spread_pct, self.fee_pct)["total_eur"]
                            qty = size["amount_eur"] / price
                            cash -= size["amount_eur"] + costs
                            position = {
                                "qty": qty,
                                "entry": price,
                                "stop": size["stop_loss_eur"],
                                "tp": size["take_profit_eur"],
                                "costs": costs,
                            }

            mark = cash + (position["qty"] * price if position else 0.0)
            equity_curve.append(mark)

        # force-close open position at the last price
        if position is not None:
            last = float(close.iloc[-1])
            gross = position["qty"] * last
            costs = estimate_order_costs(gross, self.spread_pct, self.fee_pct)["total_eur"]
            cash += gross - costs
            total_costs = position["costs"] + costs
            trades.append({
                "side": "LONG", "entry": position["entry"], "exit": last,
                "qty": position["qty"], "reason": "end_of_data",
                "costs_eur": round(total_costs, 4),
                "pnl_eur": round(position["qty"] * (last - position["entry"]) - total_costs, 4),
            })
            equity_curve[-1] = cash

        report = summary(equity_curve, trades)
        report["symbol"] = self.symbol
        report["fee_pct"] = self.fee_pct
        report["spread_pct"] = self.spread_pct
        return {"report": report, "equity_curve": equity_curve, "trades": trades}
