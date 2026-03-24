"""
risk_manager.py
Regole di rischio, segnali operativi e raccomandazioni.
Output: raccomandazioni human-readable per esecuzione manuale su app Revolut.
"""

import json
from datetime import datetime

from src.market_data import MarketDataClient
from src.portfolio import PortfolioAnalyzer


RISK_ICONS = {"low": "🟢", "medium": "🟡", "high": "🔴"}


class RiskManager:
    def __init__(self, config_path: str = "config.json"):
        with open(config_path) as f:
            self.config = json.load(f)
        self.market = MarketDataClient(config_path)
        self.portfolio = PortfolioAnalyzer(config_path=config_path)

    # ─── Valutazione rischio posizione ───────────────────────────────────────

    def assess_position_risk(self, symbol: str, asset_type: str = "stock") -> str:
        """Valuta il livello di rischio di un asset."""
        if asset_type == "crypto":
            return "high"
        if asset_type == "commodity":
            return "medium"
        analysis = self.market.full_analysis(symbol)
        rsi = analysis.get("rsi_14", 50)
        vol_ratio = analysis.get("volume_ratio", 1.0)
        if rsi > 70 or rsi < 25 or vol_ratio >= 2.5:
            return "high"
        if vol_ratio >= 1.5 or abs(analysis.get("change_pct", 0)) > 3:
            return "medium"
        return "low"

    # ─── Raccomandazioni operative ────────────────────────────────────────────

    def generate_recommendation(self, symbol: str, asset_type: str = "stock") -> dict:
        """
        Genera una raccomandazione operativa completa per un asset.
        Include istruzioni per esecuzione manuale su app Revolut.
        """
        analysis = self.market.full_analysis(symbol)
        if "error" in analysis:
            return {"symbol": symbol, "error": analysis["error"]}

        risk_level = self.assess_position_risk(symbol, asset_type)
        signal = analysis.get("technical_signal", "HOLD")
        price = analysis["price"]
        rsi = analysis.get("rsi_14", 50)

        # Stop loss e take profit
        stop_loss_pct = self.config["risk_rules"]["default_stop_loss_pct"] / 100
        take_profit_pct = self.config["risk_rules"]["default_take_profit_pct"] / 100
        stop_loss_price = round(price * (1 + stop_loss_pct), 4)
        take_profit_price = round(price * (1 + take_profit_pct), 4)

        # Costruzione motivazione
        reasons = []
        if rsi < 30:
            reasons.append(f"RSI={rsi} (ipervenduto)")
        elif rsi > 70:
            reasons.append(f"RSI={rsi} (ipercomprato)")
        if analysis.get("volume_alert"):
            reasons.append(f"Volume anomalo ({analysis['volume_ratio']}x media)")
        if analysis.get("change_pct", 0) < -5:
            reasons.append(f"Calo giornaliero significativo ({analysis['change_pct']}%)")

        motivation = "; ".join(reasons) if reasons else "Nessun segnale tecnico forte al momento."

        # Istruzioni manuali per app Revolut
        if signal == "BUY":
            manual_instructions = (
                f"Nell'app Revolut: Investimenti → Cerca '{symbol}' → "
                f"Acquista → Inserisci importo → Conferma"
            )
        elif signal in ("SELL", "SELL/TRIM"):
            manual_instructions = (
                f"Nell'app Revolut: Investimenti → Il mio portafoglio → "
                f"Seleziona '{symbol}' → Vendi → Inserisci quantità → Conferma"
            )
        else:
            manual_instructions = "Nessuna azione richiesta al momento."

        return {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "asset_type": asset_type,
            "signal": signal,
            "risk_level": risk_level,
            "risk_icon": RISK_ICONS[risk_level],
            "current_price": price,
            "currency": analysis.get("currency", "USD"),
            "motivation": motivation,
            "stop_loss": stop_loss_price,
            "take_profit": take_profit_price,
            "rsi_14": rsi,
            "week_change_pct": analysis.get("week_change_pct"),
            "month_change_pct": analysis.get("month_change_pct"),
            "manual_instructions": manual_instructions,
            "disclaimer": "⚠️ Analisi algoritmica — non consulenza finanziaria MiFID II.",
        }

    # ─── Analisi rischio portafoglio ─────────────────────────────────────────

    def portfolio_risk_report(self) -> dict:
        """
        Analisi completa del rischio del portafoglio corrente.
        Identifica squilibri e suggerisce ribilanciamento.
        """
        snapshot = self.portfolio.snapshot()
        totals = snapshot["totals"]
        concentration = snapshot["concentration"]
        alerts = snapshot["alerts"]

        issues = []
        suggestions = []

        # Cash reserve
        if alerts["cash_below_minimum"]:
            issues.append(
                f"⚠️ Cash ({alerts['cash_pct']:.1f}%) sotto il minimo consigliato "
                f"({alerts['min_cash_pct']}%)"
            )
            suggestions.append("Considera di liquidare parzialmente le posizioni sovrapesate.")

        # Concentrazione
        for pos in alerts["overweight_positions"]:
            issues.append(
                f"⚠️ {pos['symbol']} sovrappesato ({pos['weight_pct']:.1f}% — "
                f"max consigliato: {self.config['risk_rules']['max_single_position_pct']}%)"
            )
            suggestions.append(
                f"Trim parziale di {pos['symbol']}: vendi la quota eccedente il "
                f"{self.config['risk_rules']['max_single_position_pct']}%."
            )

        overall_risk = "high" if len(issues) >= 2 else ("medium" if issues else "low")

        return {
            "timestamp": datetime.now().isoformat(),
            "overall_risk": overall_risk,
            "risk_icon": RISK_ICONS[overall_risk],
            "total_portfolio_eur": totals["total_portfolio_eur"],
            "pl_pct": totals["pl_pct"],
            "cash_pct": totals["cash_pct"],
            "issues": issues,
            "suggestions": suggestions,
            "concentration": concentration,
        }

    # ─── Ribilanciamento ─────────────────────────────────────────────────────

    def rebalance_suggestions(self) -> list[dict]:
        """
        Suggerisce operazioni di ribilanciamento basate sulla configurazione.
        Output: lista di operazioni suggerite (da eseguire manualmente).
        """
        concentration = self.portfolio.get_concentration()
        totals = self.portfolio.get_total_value()
        max_pct = self.config["risk_rules"]["max_single_position_pct"]
        suggestions = []

        for pos in concentration:
            if pos["overweight"]:
                target_value = totals["total_portfolio_eur"] * (max_pct / 100)
                excess = pos["current_value"] - target_value
                suggestions.append({
                    "action": "SELL/TRIM",
                    "symbol": pos["symbol"],
                    "reason": f"Posizione al {pos['weight_pct']:.1f}% — target {max_pct}%",
                    "amount_eur": round(excess, 2),
                    "risk_level": "medium",
                    "manual_instructions": (
                        f"App Revolut → Investimenti → {pos['symbol']} → "
                        f"Vendi → Inserisci €{excess:.2f} → Conferma"
                    ),
                })

        return suggestions
