"""OrderRouter — dispatches trade signals to the right broker.

Routing table:
    CRYPTO_ASSETS  → RevolutXClient  (BTC-USD, ETH-USD, SOL-USD)
    ALPACA_ASSETS  → AlpacaClient    (stocks + ETF USA + ASML)
    WATCH_ONLY     → log only, no order placed

Add/remove symbols here as your portfolio evolves.
"""

from __future__ import annotations

import logging

from core.alpaca_client import AlpacaClient
from core.revolut_x_client import RevolutXClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Routing sets — keep in sync with config.py ASSETS
# ---------------------------------------------------------------------------

CRYPTO_ASSETS: frozenset[str] = frozenset({
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
})

ALPACA_ASSETS: frozenset[str] = frozenset({
    # ETF USA
    "VOO", "QQQ", "TLT", "GLD", "SLV",
    # Stocks USA
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META",
    "JPM", "BAC",
    # International on US exchanges
    "ASML",
})

# These are monitored (sentiment/forecast) but never executed
WATCH_ONLY: frozenset[str] = frozenset({
    "ENI.MI",
    "CL=F",
    "^GDAXI",
})


class OrderRouter:
    """Single entry point for order execution."""

    def __init__(self) -> None:
        self._revolut = RevolutXClient()
        self._alpaca = AlpacaClient()

    # ------------------------------------------------------------------

    def execute(self, signal: dict, paper: bool = True) -> dict:
        """
        Route a validated signal to the correct broker.

        signal keys expected:
            symbol      str   e.g. "BTC-USD"
            action      str   "BUY" | "SELL" | "TRIM"
            amount_eur  float trade size in EUR
            price_eur   float current price in EUR (used for qty calc)

        Returns an order result dict.
        """
        symbol: str = signal["symbol"]
        action: str = signal["action"] if signal["action"] != "TRIM" else "SELL"
        amount_eur: float = signal["amount_eur"]
        price_eur: float = signal.get("price_eur", 1.0)

        # --- Watch only ---
        if symbol in WATCH_ONLY:
            logger.info("[WATCH_ONLY] %s — signal=%s, no order placed", symbol, action)
            return {
                "status": "watch_only",
                "broker": "none",
                "symbol": symbol,
                "action": action,
                "amount_eur": amount_eur,
            }

        # --- Crypto → Revolut X ---
        if symbol in CRYPTO_ASSETS:
            return self._revolut.place_order(
                symbol=symbol,
                action=action,
                amount_eur=amount_eur,
                price_eur=price_eur,
                paper=paper,
            )

        # --- Stocks/ETF → Alpaca ---
        if symbol in ALPACA_ASSETS:
            return self._alpaca.place_order(
                symbol=symbol,
                action=action,
                amount_eur=amount_eur,
                price_eur=price_eur,
                paper=paper,
            )

        # --- Unknown asset ---
        logger.warning("OrderRouter: unknown symbol %r — order skipped", symbol)
        return {
            "status": "skipped",
            "broker": "none",
            "symbol": symbol,
            "action": action,
            "amount_eur": amount_eur,
            "error": "symbol not in any routing table",
        }
