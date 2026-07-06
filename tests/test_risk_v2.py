"""Risk manager v2 gates — kill-switch, halt, cooldown, trade/turnover limits,
cost gate integration."""

import uuid
from datetime import datetime, timezone

import pytest

import agents.risk_manager as rm
from core import config, safety
from core.db import save_orders


def _state(**overrides):
    state = {
        "cycle_id": str(uuid.uuid4())[:8],
        "mode": "paper",
        "signals": [_buy_signal()],
        "validated_signals": [],
        "portfolio": {
            "positions": [],
            "cash_eur": 500.0,
            "total_value_eur": 500.0,
            "risk_score": 0,
            "risk_label": "Basso",
            "allocations": {},
        },
        "errors": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    state.update(overrides)
    return state


def _buy_signal(symbol="BTC-USD", amount=30.0):
    return {
        "symbol": symbol, "action": "BUY", "confidence": 0.8,
        "amount_eur": amount, "reason": "test", "sentiment_score": 0.5,
        "forecast_score": 0.5, "price_eur": 50000.0,
        "stop_loss_eur": 48000.0, "take_profit_eur": 55000.0,
    }


@pytest.fixture(autouse=True)
def isolated_safety(tmp_path, monkeypatch, clean_db):
    monkeypatch.setattr(config, "KILL_SWITCH_FILE", tmp_path / "KILL")
    monkeypatch.setattr(config, "HALT_FILE", tmp_path / "HALT")
    monkeypatch.setattr(config, "SAFETY_STATE_PATH", tmp_path / "safety.json")
    monkeypatch.setattr(config, "DECISIONS_LOG_PATH", tmp_path / "decisions.jsonl")
    monkeypatch.delenv("KILL_SWITCH", raising=False)
    yield


def _actionable(result):
    return [s for s in result["validated_signals"] if s["action"] in ("BUY", "SELL", "TRIM")]


def test_normal_buy_passes():
    result = rm.run(_state())
    assert len(_actionable(result)) == 1


def test_kill_switch_blocks_everything(monkeypatch):
    monkeypatch.setenv("KILL_SWITCH", "1")
    result = rm.run(_state())
    assert _actionable(result) == []


def test_circuit_breaker_halts_trading():
    safety.check_drawdown(1000.0)  # HWM 1000; equity 500 → -50% → halt
    result = rm.run(_state())
    assert _actionable(result) == []
    assert safety.halt_active()


def test_cooldown_blocks_repeat_trade():
    # a trade on BTC-USD just executed
    save_orders("prev", [{
        "order_id": "x", "symbol": "BTC-USD", "action": "BUY",
        "amount_eur": 20.0, "price_eur": 50000.0, "status": "simulated", "mode": "paper",
    }])
    result = rm.run(_state())
    assert _actionable(result) == []
    # a different symbol is NOT in cooldown
    result2 = rm.run(_state(signals=[_buy_signal(symbol="ETH-USD")]))
    assert len(_actionable(result2)) == 1


def test_max_trades_per_day(monkeypatch):
    monkeypatch.setattr(rm, "MAX_TRADES_PER_DAY", 2)
    save_orders("prev", [
        {"order_id": f"x{i}", "symbol": f"S{i}", "action": "BUY",
         "amount_eur": 10.0, "price_eur": 1.0, "status": "simulated", "mode": "paper"}
        for i in range(2)
    ])
    result = rm.run(_state())
    assert _actionable(result) == []


def test_max_daily_turnover(monkeypatch):
    monkeypatch.setattr(rm, "MAX_DAILY_TURNOVER_PCT", 10.0)  # 10% di 500 = 50 €
    save_orders("prev", [{
        "order_id": "x", "symbol": "OTHER", "action": "BUY",
        "amount_eur": 40.0, "price_eur": 1.0, "status": "simulated", "mode": "paper",
    }])
    # 40 già scambiati + 30 nuovi = 70 > 50 → blocco
    result = rm.run(_state())
    assert _actionable(result) == []


def test_cost_gate_blocks_in_pipeline(monkeypatch):
    monkeypatch.setattr(config, "COST_GATE_MAX_PCT", 0.01)  # impossibile da soddisfare
    result = rm.run(_state())
    assert _actionable(result) == []


def test_hold_signals_survive_halt(monkeypatch):
    monkeypatch.setenv("KILL_SWITCH", "1")
    hold = dict(_buy_signal(), action="HOLD", amount_eur=0.0)
    result = rm.run(_state(signals=[hold, _buy_signal()]))
    assert [s["action"] for s in result["validated_signals"]] == ["HOLD"]


def test_decision_log_written(tmp_path):
    rm.run(_state())
    log = config.DECISIONS_LOG_PATH
    assert log.exists()
    content = log.read_text()
    assert '"accepted"' in content
