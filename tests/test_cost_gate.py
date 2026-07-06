"""Cost gate — fees+spread must never eat small capital."""

from core import config
from core.costs import cost_gate, estimate_order_costs, min_order_eur


def test_cost_estimate_math():
    # 100 € order, fee 0.09%, spread 0.20% (half charged = 0.10%)
    costs = estimate_order_costs(100.0, spread_pct=0.20, fee_pct=0.09)
    assert costs["fee_eur"] == 0.09
    assert costs["spread_eur"] == 0.10
    assert costs["total_eur"] == 0.19
    assert abs(costs["total_pct"] - 0.19) < 1e-9


def test_gate_passes_cheap_order():
    allowed, reason, costs = cost_gate("BTC-USD", 50.0, spread_pct=0.20, fee_pct=0.09)
    assert allowed, reason
    assert costs["total_pct"] <= config.COST_GATE_MAX_PCT


def test_gate_blocks_expensive_order():
    # wide spread on an illiquid pair: 1.2%/2 + 0.09% = 0.69% > 0.40%
    allowed, reason, _ = cost_gate("BTC-USD", 50.0, spread_pct=1.2, fee_pct=0.09)
    assert not allowed
    assert "cost-gate" in reason


def test_gate_blocks_below_min_order():
    allowed, reason, _ = cost_gate("BTC-USD", min_order_eur("BTC-USD") - 1)
    assert not allowed
    assert "min order" in reason


def test_gate_blocks_zero_amount():
    allowed, _, _ = cost_gate("BTC-USD", 0.0)
    assert not allowed


def test_gate_configurable_threshold():
    # same order passes with a looser threshold
    allowed_strict, _, _ = cost_gate("BTC-USD", 50.0, spread_pct=1.2, max_pct=0.4)
    allowed_loose, _, _ = cost_gate("BTC-USD", 50.0, spread_pct=1.2, max_pct=1.0)
    assert not allowed_strict
    assert allowed_loose
