"""
portfolio.py
Analisi del portafoglio: P&L, concentrazione, performance.
Il portafoglio viene definito manualmente in portfolio_holdings.json
(aggiornato dall'utente dopo ogni operazione nell'app Revolut).
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.market_data import MarketDataClient


class PortfolioAnalyzer:
    """Analisi e valutazione del portafoglio."""

    def __init__(
        self,
        holdings_path: str = "portfolio_holdings.json",
        config_path: str = "config.json",
    ):
        self.holdings_path = holdings_path
        self.market = MarketDataClient(config_path)
        with open(config_path) as f:
            self.config = json.load(f)

        # Carica o inizializza le posizioni
        if Path(holdings_path).exists():
            with open(holdings_path) as f:
                self.holdings = json.load(f)
        else:
            self.holdings = {"positions": [], "cash_eur": 0.0, "last_updated": None}

    def save_holdings(self):
        self.holdings["last_updated"] = datetime.now().isoformat()
        with open(self.holdings_path, "w") as f:
            json.dump(self.holdings, f, indent=2)

    # ─── Valutazione posizioni ────────────────────────────────────────────────

    def get_valued_positions(self) -> list[dict]:
        """
        Ritorna le posizioni con valori di mercato aggiornati.
        """
        positions = []
        for pos in self.holdings.get("positions", []):
            symbol = pos["symbol"]
            quote = self.market.get_quote(symbol)

            if "error" in quote:
                positions.append({**pos, "current_price": None, "pl_pct": None})
                continue

            current_price = quote["price"]
            avg_price = pos["avg_price"]
            quantity = pos["quantity"]

            current_value = current_price * quantity
            invested_value = avg_price * quantity
            pl_abs = current_value - invested_value
            pl_pct = ((current_price / avg_price) - 1) * 100 if avg_price > 0 else 0

            positions.append({
                **pos,
                "current_price": round(current_price, 4),
                "current_value": round(current_value, 2),
                "invested_value": round(invested_value, 2),
                "pl_abs": round(pl_abs, 2),
                "pl_pct": round(pl_pct, 2),
                "day_change_pct": quote.get("change_pct", 0),
                "currency": quote.get("currency", "USD"),
            })

        return positions

    def get_total_value(self) -> dict:
        """Valore totale del portafoglio (posizioni + cash)."""
        positions = self.get_valued_positions()
        total_invested = sum(p["invested_value"] for p in positions if p.get("invested_value"))
        total_current = sum(p["current_value"] for p in positions if p.get("current_value"))
        cash = self.holdings.get("cash_eur", 0.0)
        total_portfolio = total_current + cash

        return {
            "total_portfolio_eur": round(total_portfolio, 2),
            "total_invested_eur": round(total_invested, 2),
            "total_current_eur": round(total_current, 2),
            "cash_eur": round(cash, 2),
            "pl_abs": round(total_current - total_invested, 2),
            "pl_pct": round(((total_current / total_invested) - 1) * 100, 2) if total_invested > 0 else 0,
            "cash_pct": round((cash / total_portfolio) * 100, 2) if total_portfolio > 0 else 0,
        }

    # ─── Concentrazione e rischio ─────────────────────────────────────────────

    def get_concentration(self) -> list[dict]:
        """Peso percentuale di ogni posizione sul totale portafoglio."""
        positions = self.get_valued_positions()
        total = self.get_total_value()
        total_val = total["total_portfolio_eur"]
        max_pct = self.config["risk_rules"]["max_single_position_pct"]

        result = []
        for p in positions:
            if p.get("current_value"):
                weight = (p["current_value"] / total_val) * 100 if total_val > 0 else 0
                result.append({
                    "symbol": p["symbol"],
                    "weight_pct": round(weight, 2),
                    "overweight": weight > max_pct,
                    "current_value": p["current_value"],
                })

        return sorted(result, key=lambda x: x["weight_pct"], reverse=True)

    # ─── Report portafoglio ───────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """
        Snapshot completo del portafoglio per l'Orchestrator Agent.
        """
        positions = self.get_valued_positions()
        totals = self.get_total_value()
        concentration = self.get_concentration()

        # Identifica posizioni over/underweight
        overweight = [c for c in concentration if c["overweight"]]

        # Cash alert
        min_cash_pct = self.config["risk_rules"]["min_cash_reserve_pct"]
        cash_alert = totals["cash_pct"] < min_cash_pct

        return {
            "timestamp": datetime.now().isoformat(),
            "totals": totals,
            "positions": positions,
            "concentration": concentration,
            "alerts": {
                "overweight_positions": overweight,
                "cash_below_minimum": cash_alert,
                "cash_pct": totals["cash_pct"],
                "min_cash_pct": min_cash_pct,
            },
        }
