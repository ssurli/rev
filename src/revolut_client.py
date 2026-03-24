"""
revolut_client.py
Wrapper per Revolut Open Banking API (sola lettura — account personale).
Docs: https://developer.revolut.com/docs/guides/build-banking-apps
"""

import os
import json
import httpx
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


class RevolutClient:
    """Client per Revolut Open Banking API."""

    def __init__(self):
        env = os.getenv("REVOLUT_ENVIRONMENT", "sandbox")
        if env == "production":
            self.base_url = os.getenv("REVOLUT_OB_BASE_PRODUCTION", "https://oba.revolut.com")
        else:
            self.base_url = os.getenv("REVOLUT_OB_BASE_SANDBOX", "https://sandbox-oba.revolut.com")

        self.access_token = os.getenv("REVOLUT_ACCESS_TOKEN")
        self.client_id = os.getenv("REVOLUT_CLIENT_ID")
        self.client_secret = os.getenv("REVOLUT_CLIENT_SECRET")
        self.refresh_token = os.getenv("REVOLUT_REFRESH_TOKEN")

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Esegue una richiesta HTTP con gestione errori."""
        url = f"{self.base_url}{endpoint}"
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.request(method, url, headers=self.headers, **kwargs)
                if resp.status_code == 401:
                    raise PermissionError("Token scaduto o non valido. Esegui il refresh OAuth2.")
                if resp.status_code == 403:
                    raise PermissionError(f"Accesso negato a {endpoint}. Verifica i permessi dell'app.")
                if resp.status_code == 404:
                    raise ValueError(f"Endpoint non trovato: {endpoint}")
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError:
            raise ConnectionError(f"Impossibile connettersi a {self.base_url}. Verifica la connessione.")

    def refresh_access_token(self) -> str:
        """Rinnova l'access token tramite refresh token."""
        url = f"{self.base_url}/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        with httpx.Client() as client:
            resp = client.post(url, data=data)
            resp.raise_for_status()
            tokens = resp.json()
            self.access_token = tokens["access_token"]
            # Aggiorna .env in memoria
            os.environ["REVOLUT_ACCESS_TOKEN"] = self.access_token
            return self.access_token

    # ─── Accounts ────────────────────────────────────────────────────────────

    def get_accounts(self) -> list[dict]:
        """Ritorna la lista di tutti i conti."""
        data = self._request("GET", "/aisp/accounts")
        return data.get("Account", [])

    def get_account_balances(self) -> list[dict]:
        """Ritorna i saldi di tutti i conti."""
        data = self._request("GET", "/aisp/balances")
        return data.get("Balance", [])

    def get_account_balance(self, account_id: str) -> dict:
        """Ritorna il saldo di un conto specifico."""
        data = self._request("GET", f"/aisp/accounts/{account_id}/balances")
        balances = data.get("Balance", [])
        return balances[0] if balances else {}

    # ─── Transactions ─────────────────────────────────────────────────────────

    def get_transactions(
        self,
        account_id: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        """
        Ritorna le transazioni di un conto.
        from_date / to_date formato: 'YYYY-MM-DD'
        """
        if not from_date:
            from_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00Z")
        if not to_date:
            to_date = datetime.now().strftime("%Y-%m-%dT23:59:59Z")

        params = {"fromBookingDateTime": from_date, "toBookingDateTime": to_date}
        data = self._request(
            "GET",
            f"/aisp/accounts/{account_id}/transactions",
            params=params,
        )
        return data.get("Transaction", [])

    def get_recent_transactions(self, account_id: str, days: int = 30) -> list[dict]:
        """Ritorna le transazioni degli ultimi N giorni."""
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
        return self.get_transactions(account_id, from_date=from_date)

    # ─── Portfolio helper (da transazioni) ───────────────────────────────────

    def build_portfolio_from_transactions(self, account_id: str) -> dict:
        """
        Ricostruisce il portafoglio dalle transazioni di investimento.
        Nota: Revolut non espone direttamente le posizioni via Open Banking.
        Questo metodo inferisce le posizioni dalle transazioni di tipo 'trade'.
        """
        transactions = self.get_transactions(account_id)
        holdings: dict[str, dict] = {}

        for tx in transactions:
            tx_type = tx.get("TransactionInformation", "").lower()
            # Cerca transazioni di tipo investimento
            if any(k in tx_type for k in ["buy", "sell", "stock", "etf", "crypto"]):
                amount = float(tx.get("Amount", {}).get("Amount", 0))
                currency = tx.get("Amount", {}).get("Currency", "EUR")
                credit_debit = tx.get("CreditDebitIndicator", "")

                # Parsing base del nome asset dal campo descrizione
                description = tx.get("TransactionInformation", "")

                if description not in holdings:
                    holdings[description] = {
                        "description": description,
                        "currency": currency,
                        "total_invested": 0.0,
                        "total_sold": 0.0,
                        "transaction_count": 0,
                    }

                if credit_debit == "Debit":
                    holdings[description]["total_invested"] += amount
                else:
                    holdings[description]["total_sold"] += amount
                holdings[description]["transaction_count"] += 1

        return holdings

    # ─── Utility ─────────────────────────────────────────────────────────────

    def get_portfolio_summary(self) -> dict:
        """
        Ritorna un summary del portafoglio completo:
        saldi per valuta + lista transazioni recenti.
        """
        accounts = self.get_accounts()
        balances = self.get_account_balances()

        summary = {
            "timestamp": datetime.now().isoformat(),
            "accounts": accounts,
            "balances": [],
            "total_eur": 0.0,
        }

        for bal in balances:
            amount = float(bal.get("Amount", {}).get("Amount", 0))
            currency = bal.get("Amount", {}).get("Currency", "EUR")
            bal_type = bal.get("Type", "")
            summary["balances"].append({
                "currency": currency,
                "amount": amount,
                "type": bal_type,
            })
            if currency == "EUR":
                summary["total_eur"] += amount

        return summary

    def health_check(self) -> bool:
        """Verifica che le credenziali siano valide."""
        try:
            self.get_accounts()
            return True
        except Exception:
            return False
