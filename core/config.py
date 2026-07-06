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

# ---------------------------------------------------------------------------
# v2 — Autonomous small-capital trading (50–2000 €)
# ---------------------------------------------------------------------------

# Cost gate: block any order whose estimated cost (fee + half-spread)
# exceeds this % of the order size. Small capital → fees are enemy #1.
COST_GATE_MAX_PCT: float = _float("COST_GATE_MAX_PCT", 0.40)
TAKER_FEE_PCT: float = _float("TAKER_FEE_PCT", 0.09)        # Revolut X taker fee
DEFAULT_SPREAD_PCT: float = _float("DEFAULT_SPREAD_PCT", 0.20)  # fallback if no live quote

# Minimum order size (EUR) — Revolut X pair minimums vary; keep a safe floor
MIN_ORDER_EUR: float = _float("MIN_ORDER_EUR", 10.0)

# Anti-overtrading
TRADE_COOLDOWN_MINUTES: int = _int("TRADE_COOLDOWN_MINUTES", 240)
MAX_TRADES_PER_DAY: int = _int("MAX_TRADES_PER_DAY", 6)
MAX_DAILY_TURNOVER_PCT: float = _float("MAX_DAILY_TURNOVER_PCT", 30.0)  # % of equity

# Risk per trade: max % of equity lost if the stop is hit
RISK_PER_TRADE_PCT: float = _float("RISK_PER_TRADE_PCT", 1.0)
ATR_STOP_MULT: float = _float("ATR_STOP_MULT", 2.0)
ATR_TP_MULT: float = _float("ATR_TP_MULT", 3.0)
MAX_CASH_PER_TRADE_PCT: float = _float("MAX_CASH_PER_TRADE_PCT", 30.0)  # never >30% cash in one op

# Drawdown circuit-breaker: flat & halt if equity drops this % below high-water mark
MAX_DRAWDOWN_HALT_PCT: float = _float("MAX_DRAWDOWN_HALT_PCT", 10.0)

# Kill-switch / halt files (checked every cycle; halt requires manual unlock)
DATA_DIR: Path = Path(os.getenv("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
KILL_SWITCH_FILE: Path = Path(os.getenv("KILL_SWITCH_FILE", str(DATA_DIR / "KILL")))
HALT_FILE: Path = Path(os.getenv("HALT_FILE", str(DATA_DIR / "HALT")))
SAFETY_STATE_PATH: Path = Path(os.getenv("SAFETY_STATE_PATH", str(DATA_DIR / "safety_state.json")))

# Live-mode gates: double confirmation + capital hard-cap
LIVE_TRADING_CONFIRM: str = os.getenv("LIVE_TRADING_CONFIRM", "")  # must be "YES"
LIVE_MAX_CAPITAL_EUR: float = _float("LIVE_MAX_CAPITAL_EUR", 500.0)

# Observability
DECISIONS_LOG_PATH: Path = Path(os.getenv("DECISIONS_LOG_PATH", str(DATA_DIR / "decisions.jsonl")))
STATUS_JSON_PATH: Path = Path(os.getenv("STATUS_JSON_PATH", str(DATA_DIR / "status.json")))

# SMTP alerts (Zimbra or any SMTP server) — disabled if SMTP_HOST empty
SMTP_HOST: str = os.getenv("SMTP_HOST", "")
SMTP_PORT: int = _int("SMTP_PORT", 587)
SMTP_USER: str = os.getenv("SMTP_USER", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
ALERT_EMAIL_FROM: str = os.getenv("ALERT_EMAIL_FROM", SMTP_USER)
ALERT_EMAIL_TO: str = os.getenv("ALERT_EMAIL_TO", "")

# Signal module toggles (each analysis component can be switched off)
ENABLE_TECHNICAL: bool = _bool("ENABLE_TECHNICAL", True)
ENABLE_SENTIMENT: bool = _bool("ENABLE_SENTIMENT", True)
ENABLE_FORECAST: bool = _bool("ENABLE_FORECAST", True)
ENABLE_REGIME_FILTER: bool = _bool("ENABLE_REGIME_FILTER", True)

# Tax accounting method for Quadro RT (documented, keep consistent across years)
TAX_LOT_METHOD: str = os.getenv("TAX_LOT_METHOD", "LIFO")  # LIFO per normativa cripto-attività

# Cycle
CYCLE_INTERVAL_MINUTES: int = _int("CYCLE_INTERVAL_MINUTES", 30)

# DB
DB_PATH: Path = Path(os.getenv("DB_PATH", "./data/bot.sqlite"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
