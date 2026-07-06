"""Kill-switch, drawdown circuit-breaker, live gates."""

from pathlib import Path

import pytest

from core import config, safety


@pytest.fixture()
def tmp_safety(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "KILL_SWITCH_FILE", tmp_path / "KILL")
    monkeypatch.setattr(config, "HALT_FILE", tmp_path / "HALT")
    monkeypatch.setattr(config, "SAFETY_STATE_PATH", tmp_path / "safety_state.json")
    monkeypatch.delenv("KILL_SWITCH", raising=False)
    yield tmp_path


def test_kill_switch_via_file(tmp_safety: Path):
    assert not safety.kill_switch_active()
    config.KILL_SWITCH_FILE.write_text("stop")
    assert safety.kill_switch_active()


def test_kill_switch_via_env(tmp_safety, monkeypatch):
    monkeypatch.setenv("KILL_SWITCH", "1")
    assert safety.kill_switch_active()


def test_drawdown_updates_hwm_without_halt(tmp_safety):
    halted, dd = safety.check_drawdown(200.0)
    assert not halted and dd == 0.0
    halted, dd = safety.check_drawdown(250.0)  # new high
    assert not halted and dd == 0.0


def test_drawdown_triggers_halt(tmp_safety):
    safety.check_drawdown(200.0)                      # HWM = 200
    halted, dd = safety.check_drawdown(200.0 * (1 - config.MAX_DRAWDOWN_HALT_PCT / 100) - 1)
    assert halted
    assert dd >= config.MAX_DRAWDOWN_HALT_PCT
    assert safety.halt_active()
    info = safety.halt_info()
    assert "Drawdown" in info["reason"]


def test_halt_requires_manual_unlock(tmp_safety):
    safety.check_drawdown(200.0)
    safety.check_drawdown(100.0)   # -50% → halt
    assert safety.halt_active()
    # recovery alone does NOT unlock
    halted, _ = safety.check_drawdown(210.0)
    assert halted
    # manual unlock does
    assert safety.clear_halt()
    assert not safety.halt_active()


def test_zero_equity_ignored(tmp_safety):
    """API failure (equity 0) must not poison the high-water mark."""
    safety.check_drawdown(200.0)
    halted, dd = safety.check_drawdown(0.0)
    assert not halted and dd == 0.0
    assert not safety.halt_active()


def test_live_gates(monkeypatch):
    # missing CLI confirm
    ok, reason = safety.live_trading_allowed(100.0, cli_confirm=False)
    assert not ok and "confirm-live" in reason
    # missing env confirm
    monkeypatch.setattr(config, "LIVE_TRADING_CONFIRM", "")
    ok, reason = safety.live_trading_allowed(100.0, cli_confirm=True)
    assert not ok and "LIVE_TRADING_CONFIRM" in reason
    # hard-cap exceeded
    monkeypatch.setattr(config, "LIVE_TRADING_CONFIRM", "YES")
    ok, reason = safety.live_trading_allowed(config.LIVE_MAX_CAPITAL_EUR + 1, cli_confirm=True)
    assert not ok and "hard-cap" in reason
    # all gates satisfied
    ok, _ = safety.live_trading_allowed(100.0, cli_confirm=True)
    assert ok
