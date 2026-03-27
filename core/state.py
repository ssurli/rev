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


class TechnicalIndicators(TypedDict):
    symbol: str
    rsi: float              # 0-100
    ma20: float             # 20-period moving average
    ma50: float             # 50-period moving average
    ma_cross: str           # golden | death | neutral
    macd: float             # MACD line
    macd_signal: float      # MACD signal line
    macd_hist: float        # MACD histogram
    bb_upper: float         # Bollinger Band upper
    bb_lower: float         # Bollinger Band lower
    bb_position: float      # 0=at lower, 1=at upper
    momentum_5d: float      # % change over 5 days
    tech_score: float       # [-1, +1] weighted composite


class AssetForecast(TypedDict):
    symbol: str
    forecast_score: float   # [-1, +1] combined score
    direction: str          # BULLISH | BEARISH | NEUTRAL
    confidence: float       # 0.0 – 1.0
    horizon: str            # short | medium
    reasoning: str          # Italian explanation
    sentiment_score: float
    tech_score: float


class TradingSignal(TypedDict):
    symbol: str
    action: Literal["BUY", "SELL", "HOLD", "TRIM"]
    confidence: float
    amount_eur: float
    reason: str
    sentiment_score: float
    forecast_score: float
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
    risk_score: int
    risk_label: str
    allocations: dict[str, float]


class Order(TypedDict):
    order_id: str
    symbol: str
    action: str
    amount_eur: float
    price_eur: float
    status: str
    mode: str
    timestamp: str


class MacroIndicator(TypedDict):
    indicator_id: str   # e.g. FEDFUNDS, CPIAUCSL, ECB_MRO
    name: str           # human-readable label
    value: float
    unit: str           # %, pts, pp, idx
    country: str        # US, EU, China
    source: str         # FRED, ECB, WorldBank


class BotState(TypedDict):
    """Full state passed through the LangGraph workflow each cycle."""
    cycle_id: str
    mode: Literal["paper", "live"]
    # --- news ---
    news_items: list[NewsItem]
    # --- macro economic indicators ---
    macro_data: list[MacroIndicator]
    # --- sentiment ---
    sentiment_scores: dict[str, float]
    asset_mentions: dict[str, list[str]]
    # --- market ---
    market_data: dict[str, MarketData]
    eur_usd: float
    # --- technical analysis ---
    technical_indicators: dict[str, TechnicalIndicators]
    # --- forecast (sentiment + technical + Claude synthesis) ---
    forecasts: dict[str, AssetForecast]
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
