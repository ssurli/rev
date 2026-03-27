"""Global configuration — loaded from .env file."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, default))


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, default))


def _bool(key: str, default: bool) -> bool:
    val = os.getenv(key, str(default)).lower()
    return val in ("1", "true", "yes")


# Anthropic
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = "claude-sonnet-4-6"

# Revolut
REVOLUT_CLIENT_ID: str = os.getenv("REVOLUT_CLIENT_ID", "")
REVOLUT_CLIENT_SECRET: str = os.getenv("REVOLUT_CLIENT_SECRET", "")
REVOLUT_SANDBOX: bool = _bool("REVOLUT_SANDBOX", True)
REVOLUT_BASE_URL: str = (
    "https://sandbox-b2b.revolut.com" if REVOLUT_SANDBOX
    else "https://b2b.revolut.com"
)

# NewsAPI
NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")

# Trading
TRADING_MODE: str = os.getenv("TRADING_MODE", "paper")  # paper | live

# Risk rules (mirrored from revolut_invest_v3.html)
MAX_TRADE_EUR: float = _float("MAX_TRADE_EUR", 50.0)
MIN_PORTFOLIO_EUR: float = _float("MIN_PORTFOLIO_EUR", 20.0)
MAX_POSITION_PCT: float = _float("MAX_POSITION_PCT", 20.0)
MIN_CASH_PCT: float = _float("MIN_CASH_PCT", 15.0)
STOP_LOSS_PCT: float = _float("STOP_LOSS_PCT", -15.0)
TAKE_PROFIT_PCT: float = _float("TAKE_PROFIT_PCT", 30.0)
MAX_CRYPTO_PCT: float = _float("MAX_CRYPTO_PCT", 15.0)

# Assets
ASSETS: list[str] = [
    a.strip() for a in os.getenv("ASSETS", "BTC-USD,ETH-USD,VOO,GLD,QQQ").split(",")
]

# EUR/USD exchange rate (fallback if live fetch fails)
EUR_USD_FALLBACK: float = 1.08

# Cycle
CYCLE_INTERVAL_MINUTES: int = _int("CYCLE_INTERVAL_MINUTES", 30)

# DB
DB_PATH: Path = Path(os.getenv("DB_PATH", "./data/bot.sqlite"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
