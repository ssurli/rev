"""Tax ledger — supporto alla dichiarazione per residente fiscale italiano
in regime dichiarativo. NON è consulenza fiscale: verificare sempre con il
commercialista.

Cosa fa:
- registra ogni fill (timestamp UTC, asset, side, qty, prezzo, fee,
  controvalore EUR al cambio del momento) nella tabella `fills`;
- Quadro RT: plus/minusvalenze realizzate con metodo LIFO
  (metodo previsto per le cripto-attività, art. 67 c.1-septies ss. TUIR;
  documentato e da mantenere coerente tra gli anni);
- Quadro RW / IVAFE-imposta di bollo: giacenze di fine anno e valori
  per il monitoraggio fiscale;
- export annuale CSV/JSON pronto per il commercialista.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from core import config
from core.db import get_fills, save_fill

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Supporto alla dichiarazione, non consulenza fiscale; "
    "verificare con commercialista."
)


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def record_fill(
    order_id: str,
    cycle_id: str,
    symbol: str,
    side: str,              # BUY | SELL
    qty: float,
    price: float,           # in quote currency (e.g. USD)
    price_ccy: str,
    eur_rate: float,        # quote-ccy → EUR at fill time (USD: 1/EURUSD)
    fee_eur: float,
    broker: str,
    mode: str,
    ts_utc: str | None = None,
) -> dict:
    fill = {
        "order_id": order_id,
        "cycle_id": cycle_id,
        "ts_utc": ts_utc or datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "side": side.upper(),
        "qty": qty,
        "price": price,
        "price_ccy": price_ccy,
        "eur_rate": eur_rate,
        "countervalue_eur": round(qty * price * eur_rate, 2),
        "fee_eur": round(fee_eur, 4),
        "broker": broker,
        "mode": mode,
    }
    save_fill(fill)
    return fill


# ---------------------------------------------------------------------------
# Quadro RT — realized gains, LIFO
# ---------------------------------------------------------------------------

def compute_realized_gains(fills: list[dict]) -> list[dict]:
    """Match SELL fills against BUY lots with LIFO; return realized events.

    Cost basis includes buy fees; proceeds are net of sell fees.
    Fills must be in chronological order (get_fills guarantees it).
    """
    lots: dict[str, list[dict]] = {}   # symbol → stack of open buy lots
    realized: list[dict] = []

    for f in fills:
        sym = f["symbol"]
        if f["side"] == "BUY":
            qty = f["qty"]
            if qty <= 0:
                continue
            cost_eur = f["countervalue_eur"] + f["fee_eur"]
            lots.setdefault(sym, []).append({
                "qty": qty,
                "cost_per_unit_eur": cost_eur / qty,
                "ts_utc": f["ts_utc"],
            })
            continue

        # SELL — consume most recent lots first (LIFO)
        qty_to_match = f["qty"]
        if qty_to_match <= 0:
            continue
        proceeds_per_unit = (f["countervalue_eur"] - f["fee_eur"]) / f["qty"]
        stack = lots.setdefault(sym, [])

        while qty_to_match > 1e-12:
            if not stack:
                # sell without recorded buy (deposit/transfer in): cost 0,
                # flagged so it can be fixed manually in the export
                realized.append({
                    "symbol": sym, "ts_sell": f["ts_utc"], "ts_buy": None,
                    "qty": round(qty_to_match, 10),
                    "proceeds_eur": round(proceeds_per_unit * qty_to_match, 2),
                    "cost_eur": 0.0,
                    "gain_eur": round(proceeds_per_unit * qty_to_match, 2),
                    "warning": "nessun lotto di acquisto registrato — verificare",
                })
                qty_to_match = 0.0
                break

            lot = stack[-1]
            matched = min(qty_to_match, lot["qty"])
            proceeds = proceeds_per_unit * matched
            cost = lot["cost_per_unit_eur"] * matched
            realized.append({
                "symbol": sym,
                "ts_sell": f["ts_utc"],
                "ts_buy": lot["ts_utc"],
                "qty": round(matched, 10),
                "proceeds_eur": round(proceeds, 2),
                "cost_eur": round(cost, 2),
                "gain_eur": round(proceeds - cost, 2),
            })
            lot["qty"] -= matched
            qty_to_match -= matched
            if lot["qty"] <= 1e-12:
                stack.pop()

    return realized


def quadro_rt_report(year: int, mode: str = "live") -> dict:
    """Realized plus/minusvalenze for `year`.

    LIFO lots are built from the FULL fill history (buys in previous years
    matter), but only sales dated in `year` enter the report.
    """
    all_fills = get_fills(mode=mode)
    realized = compute_realized_gains(all_fills)
    in_year = [r for r in realized if r["ts_sell"][:4] == str(year)]

    plus = sum(r["gain_eur"] for r in in_year if r["gain_eur"] > 0)
    minus = sum(r["gain_eur"] for r in in_year if r["gain_eur"] < 0)

    return {
        "year": year,
        "method": config.TAX_LOT_METHOD,
        "events": in_year,
        "plusvalenze_eur": round(plus, 2),
        "minusvalenze_eur": round(minus, 2),
        "netto_eur": round(plus + minus, 2),
        "note": (
            f"Metodo {config.TAX_LOT_METHOD}. Le minusvalenze sono compensabili "
            "con plusvalenze della stessa natura nei 4 anni successivi. "
            + DISCLAIMER
        ),
    }


# ---------------------------------------------------------------------------
# Quadro RW / IVAFE — year-end holdings
# ---------------------------------------------------------------------------

def quadro_rw_report(year: int, mode: str = "live") -> dict:
    """Year-end holdings per asset (giacenze) for monitoraggio RW.

    Valori: costo LIFO residuo (valore iniziale) e ultimo controvalore
    noto dal ledger come proxy del valore finale — sostituire con il
    valore di mercato al 31/12 prima dell'invio.
    """
    cutoff = f"{year + 1}-01-01"
    fills = [f for f in get_fills(mode=mode) if f["ts_utc"] < cutoff]

    holdings: dict[str, dict] = {}
    lots: dict[str, list[dict]] = {}
    last_price_eur: dict[str, float] = {}

    for f in fills:
        sym = f["symbol"]
        if f["qty"] > 0:
            last_price_eur[sym] = f["countervalue_eur"] / f["qty"]
        if f["side"] == "BUY":
            lots.setdefault(sym, []).append({
                "qty": f["qty"],
                "cost_per_unit_eur": (f["countervalue_eur"] + f["fee_eur"]) / f["qty"]
                if f["qty"] > 0 else 0.0,
            })
        else:
            qty = f["qty"]
            stack = lots.setdefault(sym, [])
            while qty > 1e-12 and stack:
                lot = stack[-1]
                matched = min(qty, lot["qty"])
                lot["qty"] -= matched
                qty -= matched
                if lot["qty"] <= 1e-12:
                    stack.pop()

    for sym, stack in lots.items():
        qty = sum(l["qty"] for l in stack)
        if qty <= 1e-12:
            continue
        cost = sum(l["qty"] * l["cost_per_unit_eur"] for l in stack)
        holdings[sym] = {
            "qty": round(qty, 10),
            "costo_lifo_eur": round(cost, 2),
            "ultimo_controvalore_eur": round(qty * last_price_eur.get(sym, 0.0), 2),
        }

    return {
        "year": year,
        "holdings": holdings,
        "note": (
            "Quadro RW: indicare giacenze e valore al 31/12 (sostituire "
            "'ultimo_controvalore_eur' con il valore di mercato al 31/12). "
            "Per le cripto-attività si applica l'imposta di bollo del 2‰ "
            "sul valore di fine anno. " + DISCLAIMER
        ),
    }


# ---------------------------------------------------------------------------
# Annual export
# ---------------------------------------------------------------------------

def export_annual(year: int, out_dir: str | Path = "exports", mode: str = "live") -> list[Path]:
    """Write fills CSV + Quadro RT CSV/JSON + Quadro RW JSON for `year`."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # Fills CSV
    fills = get_fills(year=year, mode=mode)
    fills_path = out / f"fills_{year}.csv"
    with open(fills_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ts_utc", "symbol", "side", "qty", "price", "price_ccy",
                         "eur_rate", "countervalue_eur", "fee_eur", "broker", "mode", "order_id"])
        for f in fills:
            writer.writerow([f["ts_utc"], f["symbol"], f["side"], f["qty"], f["price"],
                             f["price_ccy"], f["eur_rate"], f["countervalue_eur"],
                             f["fee_eur"], f["broker"], f["mode"], f["order_id"]])
    written.append(fills_path)

    # Quadro RT
    rt = quadro_rt_report(year, mode=mode)
    rt_json = out / f"quadro_rt_{year}.json"
    rt_json.write_text(json.dumps(rt, indent=2, ensure_ascii=False))
    written.append(rt_json)

    rt_csv = out / f"quadro_rt_{year}.csv"
    with open(rt_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["symbol", "ts_buy", "ts_sell", "qty",
                         "cost_eur", "proceeds_eur", "gain_eur", "warning"])
        for r in rt["events"]:
            writer.writerow([r["symbol"], r.get("ts_buy") or "", r["ts_sell"], r["qty"],
                             r["cost_eur"], r["proceeds_eur"], r["gain_eur"],
                             r.get("warning", "")])
    written.append(rt_csv)

    # Quadro RW
    rw = quadro_rw_report(year, mode=mode)
    rw_json = out / f"quadro_rw_{year}.json"
    rw_json.write_text(json.dumps(rw, indent=2, ensure_ascii=False))
    written.append(rw_json)

    logger.info("Export fiscale %d: %s", year, [str(p) for p in written])
    return written


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export fiscale annuale")
    parser.add_argument("--year", type=int, default=datetime.now().year - 1)
    parser.add_argument("--mode", choices=["paper", "live"], default="live")
    parser.add_argument("--out", default="exports")
    args = parser.parse_args()

    from core.db import init_db
    init_db()
    paths = export_annual(args.year, out_dir=args.out, mode=args.mode)
    print(f"\n{DISCLAIMER}\n")
    for p in paths:
        print(f"  → {p}")
