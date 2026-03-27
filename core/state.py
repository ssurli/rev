"""LangGraph shared state schema for the investment bot."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class NewsItem(TypedDict):
    title: str
    source: str
    url: str
    published_at: str
    raw_text: str


class MarketData(TypedDict):
    symbol: str
    price_eur: float
    change_pct_24h: float
    volume: float
    price_1h_ago: float
    asset_type: str  # crypto | etf | stock | commodity


class TradingSignal(TypedDict):
    symbol: str
    action: Literal["BUY", "SELL", "HOLD", "TRIM"]
    confidence: float   # 0.0 – 1.0
    amount_eur: float   # how much to buy/sell
    reason: str
    sentiment_score: float
    price_eur: float


class Position(TypedDict):
    symbol: str
    qty: float
    avg_price_eur: float
    current_price_eur: float
    value_eur: float
    pnl_pct: float
    asset_type: str


class PortfolioSnapshot(TypedDict):
    positions: list[Position]
    cash_eur: float
    total_value_eur: float
    risk_score: int        # 0-100 (revolut_invest_v3 formula)
    risk_label: str        # Basso | Medio | Alto
    allocations: dict[str, float]   # symbol -> % of total


class Order(TypedDict):
    order_id: str
    symbol: str
    action: str
    amount_eur: float
    price_eur: float
    status: str       # submitted | filled | rejected | simulated
    mode: str         # paper | live
    timestamp: str


class BotState(TypedDict):
    """Full state passed through the LangGraph workflow each cycle."""
    cycle_id: str
    mode: Literal["paper", "live"]
    # --- news ---
    news_items: list[NewsItem]
    # --- sentiment ---
    sentiment_scores: dict[str, float]      # symbol -> [-1.0, 1.0]
    asset_mentions: dict[str, list[str]]    # symbol -> [headline, ...]
    # --- market ---
    market_data: dict[str, MarketData]      # symbol -> data
    eur_usd: float
    # --- strategy ---
    signals: list[TradingSignal]
    # --- risk ---
    validated_signals: list[TradingSignal]
    # --- portfolio ---
    portfolio: PortfolioSnapshot
    # --- execution ---
    executed_orders: list[Order]
    # --- meta ---
    errors: list[str]
    timestamp: str
