"""End-to-end paper trading test — no real API calls."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

# Minimal env so config doesn't blow up
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("TRADING_MODE", "paper")
os.environ.setdefault("DB_PATH", "/tmp/test_bot.sqlite")
os.environ.setdefault("ASSETS", "BTC-USD,VOO")

from core.db import init_db
from core.state import BotState


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield


def _base_state() -> BotState:
    from datetime import datetime, timezone
    import uuid
    return BotState(
        cycle_id=str(uuid.uuid4())[:8],
        mode="paper",
        news_items=[],
        sentiment_scores={},
        asset_mentions={},
        market_data={},
        eur_usd=1.08,
        signals=[],
        validated_signals=[],
        portfolio={
            "positions": [],
            "cash_eur": 200.0,
            "total_value_eur": 200.0,
            "risk_score": 0,
            "risk_label": "Basso",
            "allocations": {},
        },
        executed_orders=[],
        errors=[],
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def test_risk_score_clean_portfolio():
    from agents.risk_manager import compute_risk_score
    portfolio = {
        "positions": [],
        "cash_eur": 200.0,
        "total_value_eur": 200.0,
    }
    score, label = compute_risk_score(portfolio)
    assert score == 0
    assert label == "Basso"


def test_risk_score_low_cash():
    from agents.risk_manager import compute_risk_score
    portfolio = {
        "positions": [
            {"symbol": "BTC-USD", "value_eur": 180.0, "asset_type": "crypto"},
        ],
        "cash_eur": 20.0,
        "total_value_eur": 200.0,
    }
    score, label = compute_risk_score(portfolio)
    # low cash (+25) + high crypto (+20) + overweight BTC (+15) = 60
    assert score >= 60
    assert label == "Alto"


def test_risk_manager_blocks_buy_on_high_risk():
    from agents.risk_manager import run
    state = _base_state()
    # Portfolio: almost all BTC (triggers low cash +25, high crypto +20, overweight +15 = 60 → Alto)
    state["portfolio"]["positions"] = [
        {"symbol": "BTC-USD", "qty": 0.004, "avg_price_eur": 40000.0,
         "current_price_eur": 45000.0, "value_eur": 180.0, "pnl_pct": 12.5, "asset_type": "crypto"}
    ]
    state["portfolio"]["cash_eur"] = 20.0
    state["portfolio"]["total_value_eur"] = 200.0
    state["signals"] = [
        {
            "symbol": "BTC-USD", "action": "BUY", "confidence": 0.9,
            "amount_eur": 30.0, "reason": "test", "sentiment_score": 0.8, "price_eur": 50000.0,
        }
    ]
    result = run(state)
    actionable = [s for s in result["validated_signals"] if s["action"] == "BUY"]
    assert len(actionable) == 0, "BUY should be blocked when risk is Alto"


def test_execution_paper_mode():
    from core.revolut_client import RevolutClient
    client = RevolutClient()
    client.authenticate()
    order = client.place_order("BTC-USD", "BUY", 30.0, 50000.0)
    assert order["status"] == "simulated"
    assert order["mode"] == "paper"
    assert order["symbol"] == "BTC-USD"


def test_strategy_stop_loss_signal():
    from agents.strategy import run
    state = _base_state()
    state["market_data"] = {
        "BTC-USD": {
            "symbol": "BTC-USD", "price_eur": 40000.0, "change_pct_24h": -20.0,
            "volume": 1000, "price_1h_ago": 41000.0, "asset_type": "crypto",
        }
    }
    state["sentiment_scores"] = {"BTC-USD": 0.0}
    state["portfolio"]["positions"] = [
        {"symbol": "BTC-USD", "qty": 0.001, "avg_price_eur": 50000.0,
         "current_price_eur": 40000.0, "value_eur": 40.0, "pnl_pct": -20.0, "asset_type": "crypto"}
    ]
    state["portfolio"]["total_value_eur"] = 240.0
    state["portfolio"]["cash_eur"] = 200.0

    result = run(state)
    sell_signals = [s for s in result["signals"] if s["action"] == "SELL" and s["symbol"] == "BTC-USD"]
    assert len(sell_signals) > 0, "Stop-loss should generate SELL signal"
    assert "Stop-loss" in sell_signals[0]["reason"]
