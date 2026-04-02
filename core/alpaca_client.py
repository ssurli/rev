"""AlpacaClient — REST client for Alpaca Markets (stocks + ETF USA).

Docs: https://docs.alpaca.markets/reference/
Auth: API key + secret in headers.

Env vars required:
    ALPACA_API_KEY      Alpaca key ID
    ALPACA_SECRET_KEY   Alpaca secret key
    ALPACA_PAPER        "true" (default) | "false"
"""

from __future__ import annotations

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

_PAPER = os.getenv("ALPACA_PAPER", "true").lower() in ("1", "true", "yes")

_BASE_URL = (
    "https://paper-api.alpaca.markets"
    if _PAPER
    else "https://api.alpaca.markets"
)


class AlpacaClient:
    """Thin wrapper around the Alpaca v2 REST API."""

    def __init__(self) -> None:
        self._api_key = os.getenv("ALPACA_API_KEY", "")
        self._secret = os.getenv("ALPACA_SECRET_KEY", "")

        if not self._api_key or not self._secret:
            logger.warning("Alpaca: ALPACA_API_KEY / ALPACA_SECRET_KEY not set — client disabled")

    @property
    def is_ready(self) -> bool:
        return bool(self._api_key and self._secret)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._secret,
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = requests.get(
            _BASE_URL + path,
            headers=self._headers(),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        resp = requests.post(
            _BASE_URL + path,
            headers=self._headers(),
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        return self._get("/v2/account")

    def get_positions(self) -> list[dict]:
        return self._get("/v2/positions")  # type: ignore[return-value]

    def is_market_open(self) -> bool:
        try:
            clock = self._get("/v2/clock")
            return clock.get("is_open", False)
        except Exception:
            return False

    def place_order(
        self,
        symbol: str,
        action: str,       # "BUY" | "SELL"
        amount_eur: float,
        price_eur: float,
        paper: bool = _PAPER,
    ) -> dict:
        """
        Place a notional market order on Alpaca.

        `amount_eur` is converted to USD using price_eur for the notional.
        Alpaca notional orders require USD, so we use a hardcoded EUR/USD
        fallback of 1.08 unless `eur_usd` is injected.

        In paper mode: if ALPACA_PAPER=true the paper endpoint is already
        used — no additional simulation layer needed.
        """
        # Alpaca works in USD
        eur_usd = float(os.getenv("EUR_USD_RATE", "1.08"))
        notional_usd = round(amount_eur * eur_usd, 2)
        side = action.lower()  # "buy" | "sell"

        if not self.is_ready:
            # Full simulation fallback (no Alpaca keys)
            logger.info(
                "[PAPER/SIM] Alpaca %s %s ~$%.2f",
                side.upper(), symbol, notional_usd,
            )
            return {
                "status": "simulated",
                "broker": "alpaca",
                "symbol": symbol,
                "action": action,
                "amount_eur": amount_eur,
                "order_id": f"sim-{int(time.time())}",
            }

        # Check market hours for stocks (not required for crypto on Alpaca)
        if not self.is_market_open():
            logger.info(
                "Alpaca: market closed — queuing %s %s as day order",
                side.upper(), symbol,
            )
            # Still submit; Alpaca queues day orders for next open

        body = {
            "symbol": symbol,
            "notional": str(notional_usd),
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }

        try:
            data = self._post("/v2/orders", body)
            logger.info("Alpaca order placed: %s %s $%.2f id=%s",
                        side.upper(), symbol, notional_usd, data.get("id"))
            return {
                "status": "filled" if data.get("status") in ("filled", "accepted") else data.get("status", "unknown"),
                "broker": "alpaca",
                "symbol": symbol,
                "action": action,
                "amount_eur": amount_eur,
                "order_id": data.get("id", ""),
            }
        except requests.HTTPError as exc:
            logger.error("Alpaca order failed for %s: %s", symbol, exc)
            return {
                "status": "error",
                "broker": "alpaca",
                "symbol": symbol,
                "action": action,
                "amount_eur": amount_eur,
                "error": str(exc),
            }
