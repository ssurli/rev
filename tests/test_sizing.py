"""Position sizing — risk-per-trade cap, confidence scaling, min order size."""

from core import config
from core.sizing import position_size


def test_risk_per_trade_cap():
    """Loss at stop must never exceed RISK_PER_TRADE_PCT of equity."""
    res = position_size("BTC-USD", equity_eur=1000.0, cash_eur=1000.0,
                        price_eur=50000.0, confidence=1.0, atr_pct=2.0)
    assert res["amount_eur"] > 0
    max_risk = 1000.0 * config.RISK_PER_TRADE_PCT / 100.0
    assert res["risk_eur"] <= max_risk + 0.01


def test_max_trade_eur_cap():
    res = position_size("BTC-USD", equity_eur=5000.0, cash_eur=5000.0,
                        price_eur=50000.0, confidence=1.0, atr_pct=1.0)
    assert res["amount_eur"] <= config.MAX_TRADE_EUR


def test_never_more_than_30pct_of_cash():
    res = position_size("BTC-USD", equity_eur=1000.0, cash_eur=100.0,
                        price_eur=50000.0, confidence=1.0, atr_pct=2.0)
    assert res["amount_eur"] <= 100.0 * config.MAX_CASH_PER_TRADE_PCT / 100.0 + 0.01


def test_confidence_scales_size():
    hi = position_size("BTC-USD", equity_eur=300.0, cash_eur=300.0,
                       price_eur=100.0, confidence=1.0, atr_pct=3.0)
    lo = position_size("BTC-USD", equity_eur=300.0, cash_eur=300.0,
                       price_eur=100.0, confidence=0.5, atr_pct=3.0)
    assert hi["amount_eur"] > 0
    assert lo["amount_eur"] < hi["amount_eur"]


def test_below_min_order_returns_zero():
    """Tiny equity → size below pair minimum → no trade at all."""
    res = position_size("BTC-USD", equity_eur=30.0, cash_eur=30.0,
                        price_eur=50000.0, confidence=0.5, atr_pct=2.0)
    assert res["amount_eur"] == 0.0
    assert "minimo" in res["reason"]


def test_atr_drives_stop_and_tp():
    price = 100.0
    res = position_size("BTC-USD", equity_eur=1000.0, cash_eur=1000.0,
                        price_eur=price, confidence=1.0, atr_pct=2.0)
    expected_stop = price * (1 - 2.0 * config.ATR_STOP_MULT / 100.0)
    expected_tp = price * (1 + 2.0 * config.ATR_TP_MULT / 100.0)
    assert abs(res["stop_loss_eur"] - expected_stop) < 1e-6
    assert abs(res["take_profit_eur"] - expected_tp) < 1e-6


def test_fractional_qty_respects_price():
    res = position_size("BTC-USD", equity_eur=1000.0, cash_eur=1000.0,
                        price_eur=50000.0, confidence=1.0, atr_pct=2.0)
    assert 0 < res["qty"] < 1  # fractional BTC
    assert abs(res["qty"] * 50000.0 - res["amount_eur"]) < 0.01


def test_invalid_inputs():
    assert position_size("BTC-USD", 0.0, 0.0, 100.0, 1.0, 2.0)["amount_eur"] == 0.0
    assert position_size("BTC-USD", 100.0, 100.0, 0.0, 1.0, 2.0)["amount_eur"] == 0.0
