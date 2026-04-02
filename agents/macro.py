"""MacroAgent - fetches economic indicators from FRED, ECB, Eurostat, World Bank.

Sources (all free, no paid key except FRED):
  US  : FRED API (fred.stlouisfed.org) - Fed Funds, CPI, Unemployment, Yields, VIX
  EU  : ECB Data Portal + Eurostat    - ECB Rate, Euribor, HICP, Unemployment, GDP, ESI
  CN  : World Bank API                - GDP growth, CPI
  Global: World Bank                  - US/EU/JP GDP growth
"""

from __future__ import annotations

import logging

import requests

from core.config import FRED_API_KEY
from core.state import BotState, MacroIndicator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# US - FRED (series_id -> (name, unit, country))
# ---------------------------------------------------------------------------
FRED_SERIES: dict[str, tuple[str, str, str]] = {
    "FEDFUNDS":       ("Fed Funds Rate",         "%",   "US"),
    "CPIAUCSL_PC1":   ("CPI Inflazione (YoY)",   "%",   "US"),
    "UNRATE":         ("Unemployment Rate",       "%",   "US"),
    "DGS10":          ("10Y Treasury Yield",      "%",   "US"),
    "DGS2":           ("2Y Treasury Yield",       "%",   "US"),
    "T10Y2Y":         ("Yield Curve 10Y-2Y",      "pp",  "US"),
    "VIXCLS":         ("VIX Volatility Index",    "pts", "US"),
    "UMCSENT":        ("Michigan Consumer Sent.", "idx", "US"),
    "BAMLH0A0HYM2":   ("US HY Credit Spread",     "pp",  "US"),
    "INDPRO":         ("Produzione Industriale",  "%",   "US"),
    "RSXFS":          ("Vendite al Dettaglio",    "%",   "US"),
}

# ---------------------------------------------------------------------------
# EU - ECB Data Portal (flow/key -> (name, unit, country))
# ---------------------------------------------------------------------------
ECB_SERIES: dict[str, tuple[str, str, str]] = {
    "FM/B.U2.EUR.RT.MR.AA.EUR.IOB.MRO":    ("ECB Main Rate",      "%", "EU"),
    "FM/B.U2.EUR.RT.MM.EURIBOR3MD_.HSTA":  ("Euribor 3M",         "%", "EU"),
    "FM/B.U2.EUR.RT.MM.EURIBOR6MD_.HSTA":  ("Euribor 6M",         "%", "EU"),
    "ICP/M.U2.N.000000.4.ANR":             ("HICP Inflazione EU",  "%", "EU"),
}

# ---------------------------------------------------------------------------
# EU - Eurostat REST API (dataset, params, name, unit, country)
# ---------------------------------------------------------------------------
EUROSTAT_SERIES: list[tuple[str, dict, str, str, str]] = [
    (
        "une_rt_m",
        {"geo": "EA", "age": "TOTAL", "sex": "T", "s_adj": "SA", "unit": "PC_ACT"},
        "Disoccupazione Eurozona", "%", "EU",
    ),
    (
        "namq_10_gdp",
        {"geo": "EA19", "unit": "CLV_PCH_PRE", "na_item": "B1GQ", "s_adj": "SCA"},
        "PIL Eurozona (QoQ)", "%", "EU",
    ),
    (
        "ei_bsco_m",
        {"geo": "EU27_2020", "indic": "BS-ESI-I", "s_adj": "SA"},
        "ESI Economic Sentiment", "idx", "EU",
    ),
]

# ---------------------------------------------------------------------------
# Global - World Bank (country_code, indicator, name, unit, country)
# ---------------------------------------------------------------------------
WB_INDICATORS: list[tuple[str, str, str, str, str]] = [
    ("CN", "NY.GDP.MKTP.KD.ZG", "GDP Growth China",  "%", "China"),
    ("US", "NY.GDP.MKTP.KD.ZG", "GDP Growth US",     "%", "US"),
    ("EU", "NY.GDP.MKTP.KD.ZG", "GDP Growth EU",     "%", "EU"),
    ("CN", "FP.CPI.TOTL.ZG",    "CPI China",         "%", "China"),
    ("JP", "NY.GDP.MKTP.KD.ZG", "GDP Growth Japan",  "%", "Global"),
]


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def _fetch_fred(series_id: str, api_key: str) -> float | None:
    try:
        resp = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id":  series_id,
                "api_key":    api_key,
                "sort_order": "desc",
                "limit":      1,
                "file_type":  "json",
            },
            timeout=8,
        )
        resp.raise_for_status()
        obs = resp.json().get("observations", [])
        if obs:
            val = obs[0].get("value", ".")
            if val != ".":
                return float(val)
    except Exception as exc:
        logger.debug("FRED %s: %s", series_id, exc)
    return None


def _fetch_ecb(flow_key: str) -> float | None:
    try:
        url = (
            f"https://data-api.ecb.europa.eu/service/data/{flow_key}"
            "?format=jsondata&lastNObservations=1"
        )
        resp = requests.get(url, timeout=8, headers={"Accept": "application/json"})
        resp.raise_for_status()
        data = resp.json()
        datasets = data.get("dataSets", [])
        if datasets:
            series = datasets[0].get("series", {})
            if series:
                first = next(iter(series.values()))
                obs = first.get("observations", {})
                if obs:
                    last_key = sorted(obs.keys(), key=int)[-1]
                    return float(obs[last_key][0])
    except Exception as exc:
        logger.debug("ECB %s: %s", flow_key, exc)
    return None


def _fetch_eurostat(dataset: str, params: dict) -> float | None:
    try:
        url = (
            "https://ec.europa.eu/eurostat/api/dissemination"
            f"/statistics/1.0/data/{dataset}"
        )
        p = {"format": "JSON", "lang": "EN", "lastTimePeriod": "3"}
        p.update(params)
        resp = requests.get(url, params=p, timeout=10)
        resp.raise_for_status()
        values = resp.json().get("value", {})
        if values:
            for key in sorted(values.keys(), key=lambda x: int(x), reverse=True):
                val = values[key]
                if val is not None:
                    return float(val)
    except Exception as exc:
        logger.debug("Eurostat %s: %s", dataset, exc)
    return None


def _fetch_worldbank(country: str, indicator: str) -> float | None:
    try:
        url = (
            f"https://api.worldbank.org/v2/country/{country}"
            f"/indicator/{indicator}?format=json&mrv=3&per_page=3"
        )
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if len(data) > 1 and data[1]:
            for entry in data[1]:
                if entry.get("value") is not None:
                    return float(entry["value"])
    except Exception as exc:
        logger.debug("WorldBank %s/%s: %s", country, indicator, exc)
    return None


# ---------------------------------------------------------------------------
# Agent run
# ---------------------------------------------------------------------------

def run(state: BotState) -> BotState:
    """Fetch macro-economic indicators and store in state."""
    indicators: list[MacroIndicator] = []

    # US - FRED
    if FRED_API_KEY:
        for series_id, (name, unit, country) in FRED_SERIES.items():
            val = _fetch_fred(series_id, FRED_API_KEY)
            if val is not None:
                indicators.append(MacroIndicator(
                    indicator_id=series_id, name=name, value=val,
                    unit=unit, country=country, source="FRED",
                ))
    else:
        logger.debug("MacroAgent: FRED_API_KEY non configurata - skip US indicators")

    # EU - ECB
    for flow_key, (name, unit, country) in ECB_SERIES.items():
        val = _fetch_ecb(flow_key)
        if val is not None:
            indicators.append(MacroIndicator(
                indicator_id=flow_key.split("/")[-1][:20],
                name=name, value=val, unit=unit, country=country, source="ECB",
            ))

    # EU - Eurostat
    for dataset, params, name, unit, country in EUROSTAT_SERIES:
        val = _fetch_eurostat(dataset, params)
        if val is not None:
            indicators.append(MacroIndicator(
                indicator_id=f"ESTAT_{dataset[:12]}",
                name=name, value=val, unit=unit, country=country, source="Eurostat",
            ))

    # Global - World Bank
    for country_code, wb_indicator, name, unit, country in WB_INDICATORS:
        val = _fetch_worldbank(country_code, wb_indicator)
        if val is not None:
            indicators.append(MacroIndicator(
                indicator_id=f"WB_{country_code}_{wb_indicator.split('.')[-1]}",
                name=name, value=val, unit=unit, country=country, source="WorldBank",
            ))

    fetched = len(indicators)
    if fetched:
        summary = ", ".join(f"{i['indicator_id']}={i['value']:.2f}" for i in indicators[:6])
        logger.info("MacroAgent: %d indicators - %s%s",
                    fetched, summary, "..." if fetched > 6 else "")
    else:
        logger.info("MacroAgent: nessun indicatore (FRED key mancante o rete non disponibile)")

    state["macro_data"] = indicators
    return state
