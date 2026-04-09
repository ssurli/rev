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
NEWSAPI_SOURCES: str = "reuters,bloomberg,cnbc,the-wall-street-journal,financial-times,fortune"

# FRED API (Federal Reserve Economic Data — free key at fred.stlouisfed.org)
FRED_API_KEY: str = os.getenv("FRED_API_KEY", "")

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

# ---------------------------------------------------------------------------
# Whitelist of allowed asset symbols (prevents injection via .env)
# ---------------------------------------------------------------------------
ALLOWED_SYMBOLS: set[str] = {
    # Crypto
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD",
    "ADA-USD", "DOGE-USD", "AVAX-USD", "DOT-USD", "MATIC-USD",
    "LINK-USD", "LTC-USD", "UNI-USD", "ATOM-USD", "NEAR-USD",
    # ETF — US broad
    "VOO", "QQQ", "SPY", "IVV", "VTI", "RSP",
    # ETF — bond/fixed income
    "TLT", "IEF", "SHY", "HYG", "LQD",
    # ETF — settoriali
    "ARKK", "XLF", "XLE", "XLK", "XLV", "XLI", "XLB",
    # ETF — internazionali
    "EEM", "EWJ", "FXI", "VGK", "EWZ",
    # ETF — commodity
    "GLD", "SLV", "GDX", "USO",
    # Commodities futures
    "GC=F", "SI=F", "CL=F", "NG=F", "HG=F", "ZW=F", "ZC=F",
    # Forex
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCNY=X",
    # Stock — Big Tech
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA",
    # Stock — Tech
    "AMD", "INTC", "CRM", "ORCL", "ADBE", "QCOM", "ARM",
    # Stock — Finance
    "JPM", "BAC", "GS", "MS", "V", "MA", "PYPL",
    # Stock — Consumer/Retail
    "WMT", "AMZN", "NFLX", "DIS", "SBUX", "NKE",
    # Stock — Health
    "JNJ", "PFE", "ABBV", "UNH",
    # Stock — Energy
    "XOM", "CVX", "BP",
    # Stock — International (Asia)
    "BABA", "TSM", "NVO",
    # Stock — Europa (ticker Yahoo Finance, suffisso borsa)
    "ASML", "SAP",                              # già presenti
    "MC.PA",   # LVMH (Parigi)
    "OR.PA",   # L'Oréal (Parigi)
    "SIE.DE",  # Siemens (Francoforte)
    "ALV.DE",  # Allianz (Francoforte)
    "BAS.DE",  # BASF (Francoforte)
    "BMW.DE",  # BMW (Francoforte)
    "DTE.DE",  # Deutsche Telekom
    "ENEL.MI", # Enel (Milano)
    "ENI.MI",  # ENI (Milano)
    "ISP.MI",  # Intesa Sanpaolo (Milano)
    "UCG.MI",  # UniCredit (Milano)
    "STM.MI",  # STMicroelectronics (Milano)
    # ETF Europa
    "VWCE.DE", # Vanguard FTSE All-World (Xetra)
    "CSPX.L",  # iShares S&P500 (Londra)
    "IWDA.L",  # iShares MSCI World (Londra)
    "EXS1.DE", # iShares DAX (Xetra)
    "MEUD.PA", # Amundi STOXX Europe 600
    # Indices
    "^GSPC", "^DJI", "^IXIC",                  # US
    "^FTSE", "^DAX", "^GDAXI", "^FCHI", "^STOXX50E",  # Europa
    "^N225", "^HSI", "^AXJO",                  # Asia/Pacific
}

# ---------------------------------------------------------------------------
# Default ASSETS — configurable via .env ASSETS=sym1,sym2,...
# ---------------------------------------------------------------------------
_DEFAULT_ASSETS = (
    "BTC-USD,ETH-USD,SOL-USD,"
    "VOO,QQQ,TLT,"
    "GLD,SLV,CL=F,"
    "AAPL,MSFT,NVDA,TSLA,AMZN,META,"
    "JPM,BAC"
)

ASSETS: list[str] = [
    a.strip() for a in os.getenv("ASSETS", _DEFAULT_ASSETS).split(",")
    if a.strip() in ALLOWED_SYMBOLS
]

# EUR/USD exchange rate (fallback if live fetch fails)
EUR_USD_FALLBACK: float = 1.08

# Swing cycle (main)
CYCLE_INTERVAL_MINUTES: int = _int("CYCLE_INTERVAL_MINUTES", 60)

# Intraday / day-trading cycle
INTRADAY_CYCLE_MINUTES: int = _int("INTRADAY_CYCLE_MINUTES", 5)
DAY_TRADING_ENABLED:   bool = _bool("DAY_TRADING_ENABLED", False)

# DB
DB_PATH: Path = Path(os.getenv("DB_PATH", "./data/bot.sqlite"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
