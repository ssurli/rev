"""CLI backtest — python -m backtest.run_backtest --symbol BTC-USD --period 2y

Scarica candele storiche (yfinance) e produce il report metriche richiesto
prima di qualsiasi go-live.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yfinance as yf

from backtest.engine import Backtester


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest offline")
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--period", default="2y", help="yfinance period (1y, 2y, 5y...)")
    parser.add_argument("--interval", default="1d", help="candle interval (1d, 1h...)")
    parser.add_argument("--equity", type=float, default=200.0, help="capitale iniziale EUR")
    parser.add_argument("--out", default="", help="salva report JSON su file")
    args = parser.parse_args()

    hist = yf.Ticker(args.symbol).history(period=args.period, interval=args.interval)
    if hist.empty or len(hist) < 100:
        raise SystemExit(f"Dati insufficienti per {args.symbol} ({len(hist)} candele)")

    bt = Backtester(args.symbol, hist, start_equity_eur=args.equity)
    result = bt.run()
    report = result["report"]

    print(f"\n=== BACKTEST {args.symbol} — {args.period}/{args.interval} "
          f"— capitale €{args.equity:.0f} ===")
    print(f"  Rendimento totale : {report['total_return_pct']:+.2f}%")
    print(f"  Sharpe            : {report['sharpe']}")
    print(f"  Max drawdown      : {report['max_drawdown_pct']:.2f}%")
    print(f"  Trade chiusi      : {report['n_trades']}")
    print(f"  Hit rate          : {report['hit_rate']:.0%}")
    print(f"  Profit factor     : {report['profit_factor']}")
    print(f"  Costi totali      : €{report['total_costs_eur']:.2f}")
    print(f"  Fee/spread usati  : {report['fee_pct']}% / {report['spread_pct']}%\n")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"report": report, "trades": result["trades"]}, indent=2, default=str))
        print(f"Report salvato: {out}")


if __name__ == "__main__":
    main()
