"""Revolut Open Banking API client with paper-trading mock."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

import requests

from core.config import (
    REVOLUT_BASE_URL,
    REVOLUT_CLIENT_ID,
    REVOLUT_CLIENT_SECRET,
    REVOLUT_SANDBOX,
    TRADING_MODE,
)

logger = logging.getLogger(__name__)


class RevolutClient:
    """Thin wrapper around Revolut Open Banking REST API.

    In paper mode (TRADING_MODE=paper) no real HTTP calls are made;
    all order operations return simulated responses.
    """

    def __init__(self) -> None:
        self._token: str | None = None
        self._base = REVOLUT_BASE_URL

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        """Obtain an OAuth2 bearer token.  Returns True on success."""
        if TRADING_MODE == "paper":
            logger.info("[paper] Skipping Revolut OAuth — paper mode")
            self._token = "paper-token"
            return True
        try:
            resp = requests.post(
                f"{self._base}/api/1.0/auth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": REVOLUT_CLIENT_ID,
                    "client_secret": REVOLUT_CLIENT_SECRET,
                },
                timeout=10,
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
            logger.info("Revolut auth OK (sandbox=%s)", REVOLUT_SANDBOX)
            return True
        except Exception as exc:
            logger.error("Revolut auth failed: %s", exc)
            return False

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    def get_portfolio(self) -> dict:
        """Return current portfolio from Revolut (or mock data in paper mode)."""
        if TRADING_MODE == "paper":
            return self._mock_portfolio()
        try:
            resp = requests.get(
                f"{self._base}/api/trading/v1/portfolio",
                headers=self._headers(),
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("get_portfolio error: %s", exc)
            return self._mock_portfolio()

    def _mock_portfolio(self) -> dict:
        return {
            "positions": [],
            "cash_eur": 200.0,
            "total_value_eur": 200.0,
        }

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        action: str,       # BUY | SELL
        amount_eur: float,
        price_eur: float,
    ) -> dict:
        """Place a market order.  In paper mode, returns a simulated fill."""
        order_id = str(uuid.uuid4())
        if TRADING_MODE == "paper":
            logger.info("[paper] ORDER %s %s €%.2f @ €%.4f", action, symbol, amount_eur, price_eur)
            return {
                "order_id": order_id,
                "symbol": symbol,
                "action": action,
                "amount_eur": amount_eur,
                "price_eur": price_eur,
                "status": "simulated",
                "mode": "paper",
                "timestamp": datetime.utcnow().isoformat(),
            }
        try:
            payload = {
                "symbol": symbol,
                "side": action,
                "type": "MARKET",
                "amount": {"currency": "EUR", "value": str(amount_eur)},
            }
            resp = requests.post(
                f"{self._base}/api/trading/v1/orders",
                json=payload,
                headers=self._headers(),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "order_id": data.get("id", order_id),
                "symbol": symbol,
                "action": action,
                "amount_eur": amount_eur,
                "price_eur": price_eur,
                "status": data.get("state", "submitted"),
                "mode": "live",
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            logger.error("place_order error: %s", exc)
            return {
                "order_id": order_id,
                "symbol": symbol,
                "action": action,
                "amount_eur": amount_eur,
                "price_eur": price_eur,
                "status": "rejected",
                "mode": "live",
                "timestamp": datetime.utcnow().isoformat(),
            }

    def cancel_order(self, order_id: str) -> bool:
        if TRADING_MODE == "paper":
            logger.info("[paper] CANCEL %s", order_id)
            return True
        try:
            resp = requests.delete(
                f"{self._base}/api/trading/v1/orders/{order_id}",
                headers=self._headers(),
                timeout=10,
            )
            return resp.status_code in (200, 204)
        except Exception as exc:
            logger.error("cancel_order error: %s", exc)
            return False
