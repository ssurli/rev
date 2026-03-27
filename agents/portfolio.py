"""PortfolioAgent — tracks open positions, computes P&L, updates portfolio snapshot.

On first run (no DB history) uses Revolut API to load real positions.
Subsequent cycles update positions based on executed orders.
"""

from __future__ import annotations

import logging

from core.config import MAX_CRYPTO_PCT, MAX_POSITION_PCT, MIN_CASH_PCT, STOP_LOSS_PCT
from core.db import load_latest_portfolio, save_portfolio_snapshot
from core.revolut_client import RevolutClient
from core.state import BotState, Position, PortfolioSnapshot

logger = logging.getLogger(__name__)

_client = RevolutClient()


def _build_positions(raw_positions: list[dict], market_data: dict) -> list[Position]:
    positions: list[Position] = []
    for pos in raw_positions:
        sym = pos.get("symbol", "")
        qty = float(pos.get("qty", 0.0))
        avg = float(pos.get("avg_price_eur", 0.0))
        md = market_data.get(sym)
        current = md["price_eur"] if md else avg
        value = qty * current
        pnl_pct = ((current - avg) / avg * 100.0) if avg else 0.0
        asset_type = md["asset_type"] if md else pos.get("asset_type", "unknown")
        positions.append(Position(
            symbol=sym,
            qty=qty,
            avg_price_eur=avg,
            current_price_eur=current,
            value_eur=round(value, 2),
            pnl_pct=round(pnl_pct, 2),
            asset_type=asset_type,
        ))
    return positions


def _apply_orders(portfolio: PortfolioSnapshot, orders: list[dict], market_data: dict) -> PortfolioSnapshot:
    """Update portfolio in-memory based on just-executed orders."""
    positions = {p["symbol"]: dict(p) for p in portfolio.get("positions", [])}
    cash = portfolio.get("cash_eur", 0.0)

    for order in orders:
        sym = order["symbol"]
        action = order["action"]
        amount = order["amount_eur"]
        price = order["price_eur"]
        if price <= 0:
            continue
        qty_traded = amount / price

        if action == "BUY":
            cash -= amount
            if sym in positions:
                existing = positions[sym]
                total_qty = existing["qty"] + qty_traded
                existing["avg_price_eur"] = (
                    (existing["avg_price_eur"] * existing["qty"] + price * qty_traded) / total_qty
                )
                existing["qty"] = total_qty
            else:
                positions[sym] = {
                    "symbol": sym,
                    "qty": qty_traded,
                    "avg_price_eur": price,
                    "current_price_eur": price,
                    "value_eur": amount,
                    "pnl_pct": 0.0,
                    "asset_type": market_data.get(sym, {}).get("asset_type", "unknown"),
                }
        elif action in ("SELL", "TRIM"):
            cash += amount
            if sym in positions:
                existing = positions[sym]
                existing["qty"] = max(0.0, existing["qty"] - qty_traded)
                if existing["qty"] < 1e-8:
                    del positions[sym]

    new_positions = _build_positions(list(positions.values()), market_data)
    total = cash + sum(p["value_eur"] for p in new_positions)
    allocs = {p["symbol"]: round(p["value_eur"] / total * 100.0, 1) for p in new_positions} if total else {}

    return PortfolioSnapshot(
        positions=new_positions,
        cash_eur=round(cash, 2),
        total_value_eur=round(total, 2),
        risk_score=portfolio.get("risk_score", 0),
        risk_label=portfolio.get("risk_label", "Basso"),
        allocations=allocs,
    )


def run(state: BotState) -> BotState:
    """Load/update portfolio and persist snapshot."""
    market_data = state.get("market_data", {})
    orders = state.get("executed_orders", [])
    cycle_id = state["cycle_id"]

    # Load last known portfolio from DB
    db_snap = load_latest_portfolio()

    if db_snap is None:
        # First run: load from Revolut API
        _client.authenticate()
        raw = _client.get_portfolio()
        raw_positions = raw.get("positions", [])
        cash = float(raw.get("cash_eur", 200.0))
        positions = _build_positions(raw_positions, market_data)
        total = cash + sum(p["value_eur"] for p in positions)
        allocs = {p["symbol"]: round(p["value_eur"] / total * 100.0, 1) for p in positions} if total else {}
        portfolio: PortfolioSnapshot = PortfolioSnapshot(
            positions=positions,
            cash_eur=cash,
            total_value_eur=round(total, 2),
            risk_score=0,
            risk_label="Basso",
            allocations=allocs,
        )
    else:
        # Reconstruct from DB snapshot
        raw_positions = db_snap.get("positions", [])
        positions = _build_positions(raw_positions, market_data)
        cash = float(db_snap.get("cash_eur", 0.0))
        total = cash + sum(p["value_eur"] for p in positions)
        allocs = {p["symbol"]: round(p["value_eur"] / total * 100.0, 1) for p in positions} if total else {}
        portfolio = PortfolioSnapshot(
            positions=positions,
            cash_eur=cash,
            total_value_eur=round(total, 2),
            risk_score=db_snap.get("risk_score", 0),
            risk_label=db_snap.get("risk_label", "Basso"),
            allocations=allocs,
        )

    # Apply executed orders
    if orders:
        portfolio = _apply_orders(portfolio, orders, market_data)

    # Persist
    save_portfolio_snapshot(cycle_id, portfolio)

    logger.info(
        "Portfolio: €%.2f total | €%.2f cash | %d positions | risk=%d %s",
        portfolio["total_value_eur"], portfolio["cash_eur"],
        len(portfolio["positions"]), portfolio["risk_score"], portfolio["risk_label"],
    )

    state["portfolio"] = portfolio
    return state
