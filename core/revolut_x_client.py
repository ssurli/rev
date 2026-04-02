"""RevolutXClient — REST client for Revolut X crypto exchange.

Docs: https://developer.revolut.com/docs/x-api/revolut-x-crypto-exchange-rest-api
Auth: Ed25519 signature on every request.

Env vars required:
    REVOLUT_X_PRIVATE_KEY_PATH  path to Ed25519 private key PEM file
    REVOLUT_X_BASE_URL          (optional) override base URL
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path

import requests
from cryptography.hazmat.primitives import serialization
from nacl.signing import SigningKey

logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("REVOLUT_X_BASE_URL", "https://api.revolut.com/api/1.0")

# Revolut X symbol format: "BTC/USD"  (our internal format: "BTC-USD")
def _to_revx_symbol(symbol: str) -> str:
    return symbol.replace("-", "/")


class RevolutXClient:
    """Thin wrapper around the Revolut X REST API."""

    def __init__(self) -> None:
        self._signing_key: SigningKey | None = None
        self._load_key()

    # ------------------------------------------------------------------
    # Key loading
    # ------------------------------------------------------------------

    def _load_key(self) -> None:
        key_path = os.getenv("REVOLUT_X_PRIVATE_KEY_PATH", "")
        if not key_path or not Path(key_path).exists():
            logger.warning("RevolutX: private key not found at %r — client disabled", key_path)
            return

        try:
            pem_data = Path(key_path).read_bytes()
            key_obj = serialization.load_pem_private_key(pem_data, password=None)
            raw_bytes = key_obj.private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )
            self._signing_key = SigningKey(raw_bytes)
            logger.info("RevolutX: Ed25519 key loaded from %s", key_path)
        except Exception as exc:
            logger.error("RevolutX: failed to load private key: %s", exc)

    @property
    def is_ready(self) -> bool:
        return self._signing_key is not None

    # ------------------------------------------------------------------
    # Request signing
    # ------------------------------------------------------------------

    def _sign(self, method: str, path: str, body: str = "") -> dict[str, str]:
        """Return signed headers for a request."""
        ts = str(int(time.time() * 1000))
        message = f"{ts}{method.upper()}{path}{body}".encode()
        sig_bytes = self._signing_key.sign(message).signature  # type: ignore[union-attr]
        signature = base64.b64encode(sig_bytes).decode()
        return {
            "Content-Type": "application/json",
            "X-Revx-Timestamp": ts,
            "X-Revx-Signature": signature,
        }

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------

    def get_ticker(self, symbol: str) -> dict:
        """Get current best bid/ask for a symbol."""
        revx_sym = _to_revx_symbol(symbol)
        path = f"/crypto-exchange/quote?symbol={revx_sym}"
        headers = self._sign("GET", f"/api/1.0{path}")
        resp = requests.get(_BASE_URL + path, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_balances(self) -> dict:
        """Return account balances."""
        path = "/accounts"
        headers = self._sign("GET", f"/api/1.0{path}")
        resp = requests.get(_BASE_URL + path, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def place_order(
        self,
        symbol: str,
        action: str,       # "BUY" | "SELL"
        amount_eur: float,
        price_eur: float,
        paper: bool = True,
    ) -> dict:
        """
        Place a market order on Revolut X.

        In paper mode: simulates the order without hitting the API.
        qty is derived from amount_eur / price_eur.
        """
        revx_symbol = _to_revx_symbol(symbol)
        side = action.lower()  # "buy" | "sell"
        qty = round(amount_eur / price_eur, 8) if price_eur > 0 else 0.0

        if paper:
            logger.info(
                "[PAPER] RevolutX %s %s qty=%.8f (~€%.2f)",
                side.upper(), revx_symbol, qty, amount_eur,
            )
            return {
                "status": "simulated",
                "broker": "revolut_x",
                "symbol": symbol,
                "action": action,
                "amount_eur": amount_eur,
                "qty": qty,
                "order_id": f"paper-{int(time.time())}",
            }

        if not self.is_ready:
            raise RuntimeError("RevolutX client not initialised — check REVOLUT_X_PRIVATE_KEY_PATH")

        body_dict = {
            "symbol": revx_symbol,
            "type": "market",
            "side": side,
            "qty": str(qty),
        }
        body = json.dumps(body_dict, separators=(",", ":"))
        path = "/crypto-exchange/orders"
        headers = self._sign("POST", f"/api/1.0{path}", body)

        resp = requests.post(_BASE_URL + path, headers=headers, data=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        logger.info("RevolutX order placed: %s", data)
        return {
            "status": "filled",
            "broker": "revolut_x",
            "symbol": symbol,
            "action": action,
            "amount_eur": amount_eur,
            "qty": qty,
            "order_id": data.get("id", ""),
        }
