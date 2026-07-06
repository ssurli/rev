"""Tax ledger — LIFO realized gains (Quadro RT), holdings (RW), export."""

import pytest

from core.ledger import (
    compute_realized_gains,
    export_annual,
    quadro_rt_report,
    quadro_rw_report,
    record_fill,
)


def _fill(symbol, side, qty, cv_eur, fee_eur, ts):
    return {
        "symbol": symbol, "side": side, "qty": qty,
        "countervalue_eur": cv_eur, "fee_eur": fee_eur, "ts_utc": ts,
    }


def test_lifo_matches_most_recent_lot():
    fills = [
        _fill("BTC-USD", "BUY", 1.0, 100.0, 1.0, "2025-01-01T00:00:00Z"),
        _fill("BTC-USD", "BUY", 1.0, 200.0, 1.0, "2025-02-01T00:00:00Z"),
        _fill("BTC-USD", "SELL", 1.0, 150.0, 1.0, "2025-03-01T00:00:00Z"),
    ]
    realized = compute_realized_gains(fills)
    assert len(realized) == 1
    ev = realized[0]
    # LIFO: matches the Feb lot (cost 201), proceeds 149 → loss -52
    assert ev["ts_buy"].startswith("2025-02")
    assert ev["cost_eur"] == 201.0
    assert ev["proceeds_eur"] == 149.0
    assert ev["gain_eur"] == -52.0


def test_partial_lot_matching():
    fills = [
        _fill("ETH-USD", "BUY", 2.0, 200.0, 2.0, "2025-01-01T00:00:00Z"),  # 101/unit
        _fill("ETH-USD", "SELL", 0.5, 80.0, 0.5, "2025-06-01T00:00:00Z"),  # 159/unit net
    ]
    realized = compute_realized_gains(fills)
    assert len(realized) == 1
    ev = realized[0]
    assert ev["qty"] == 0.5
    assert ev["cost_eur"] == 50.5    # 0.5 × 101
    assert ev["proceeds_eur"] == 79.5
    assert abs(ev["gain_eur"] - 29.0) < 0.01


def test_sell_without_buy_is_flagged():
    fills = [_fill("SOL-USD", "SELL", 1.0, 100.0, 1.0, "2025-05-01T00:00:00Z")]
    realized = compute_realized_gains(fills)
    assert len(realized) == 1
    assert "warning" in realized[0]
    assert realized[0]["cost_eur"] == 0.0


def test_quadro_rt_year_filter_and_totals(clean_db):
    # buy in 2024, sells in 2025: only 2025 sales in the 2025 report,
    # but the 2024 lot is used as cost basis
    record_fill("o1", "c1", "BTC-USD", "BUY", 1.0, 100.0, "USD", 1.0, 1.0,
                "revolut_x", "live", ts_utc="2024-06-01T00:00:00+00:00")
    record_fill("o2", "c2", "BTC-USD", "SELL", 0.5, 90.0, "USD", 1.0, 0.5,
                "revolut_x", "live", ts_utc="2025-03-01T00:00:00+00:00")
    record_fill("o3", "c3", "BTC-USD", "SELL", 0.5, 30.0, "USD", 1.0, 0.5,
                "revolut_x", "live", ts_utc="2025-09-01T00:00:00+00:00")

    rt = quadro_rt_report(2025, mode="live")
    assert rt["method"] == "LIFO"
    assert len(rt["events"]) == 2
    # lot: qty 1, cost 101 → 50.5 per 0.5
    # sell1: proceeds 44.5, gain -6.0 | sell2: proceeds 14.5, gain -36.0
    assert rt["plusvalenze_eur"] == 0.0
    assert abs(rt["minusvalenze_eur"] - (-42.0)) < 0.01
    assert abs(rt["netto_eur"] - (-42.0)) < 0.01
    assert "commercialista" in rt["note"]

    rt_2024 = quadro_rt_report(2024, mode="live")
    assert rt_2024["events"] == []


def test_quadro_rw_holdings(clean_db):
    record_fill("o1", "c1", "ETH-USD", "BUY", 2.0, 1000.0, "USD", 1.0, 2.0,
                "revolut_x", "live", ts_utc="2025-02-01T00:00:00+00:00")
    record_fill("o2", "c2", "ETH-USD", "SELL", 0.5, 300.0, "USD", 1.0, 0.5,
                "revolut_x", "live", ts_utc="2025-08-01T00:00:00+00:00")

    rw = quadro_rw_report(2025, mode="live")
    assert "ETH-USD" in rw["holdings"]
    h = rw["holdings"]["ETH-USD"]
    assert abs(h["qty"] - 1.5) < 1e-9
    # cost: 1.5 × (2002/2) = 1501.5
    assert abs(h["costo_lifo_eur"] - 1501.5) < 0.01
    assert "commercialista" in rw["note"]


def test_export_annual_writes_files(clean_db, tmp_path):
    record_fill("o1", "c1", "BTC-USD", "BUY", 1.0, 100.0, "USD", 1.0, 1.0,
                "revolut_x", "live", ts_utc="2025-01-15T00:00:00+00:00")
    record_fill("o2", "c2", "BTC-USD", "SELL", 1.0, 120.0, "USD", 1.0, 1.0,
                "revolut_x", "live", ts_utc="2025-11-15T00:00:00+00:00")

    written = export_annual(2025, out_dir=tmp_path, mode="live")
    names = {p.name for p in written}
    assert names == {"fills_2025.csv", "quadro_rt_2025.json",
                     "quadro_rt_2025.csv", "quadro_rw_2025.json"}
    for p in written:
        assert p.exists() and p.stat().st_size > 0


def test_record_fill_eur_conversion(clean_db):
    # 0.001 BTC @ 60000 USD, EURUSD=1.10 → eur_rate 0.909090…
    fill = record_fill("o1", "c1", "BTC-USD", "BUY", 0.001, 60000.0, "USD",
                       1 / 1.10, 0.05, "revolut_x", "paper")
    assert abs(fill["countervalue_eur"] - 54.55) < 0.01
