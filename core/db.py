"""SQLite persistence layer for the investment bot."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from core.config import DB_PATH


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    """Create tables if they don't exist."""
    # Restrict DB file to owner only (rw-------)
    DB_PATH.touch(exist_ok=True)
    os.chmod(DB_PATH, 0o600)
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS news_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT UNIQUE,
            title       TEXT,
            source      TEXT,
            published_at TEXT,
            raw_text    TEXT,
            cycle_id    TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sentiment_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id    TEXT,
            symbol      TEXT,
            score       REAL,
            headlines   TEXT,    -- JSON array
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id    TEXT,
            symbol      TEXT,
            action      TEXT,
            confidence  REAL,
            amount_eur  REAL,
            reason      TEXT,
            sentiment   REAL,
            price_eur   REAL,
            validated   INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS orders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id    TEXT,
            cycle_id    TEXT,
            symbol      TEXT,
            action      TEXT,
            amount_eur  REAL,
            price_eur   REAL,
            status      TEXT,
            mode        TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id        TEXT,
            total_value_eur REAL,
            cash_eur        REAL,
            risk_score      INTEGER,
            risk_label      TEXT,
            positions_json  TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS forecasts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id        TEXT,
            symbol          TEXT,
            forecast_score  REAL,
            direction       TEXT,
            confidence      REAL,
            horizon         TEXT,
            reasoning       TEXT,
            sentiment_score REAL,
            tech_score      REAL,
            created_at      TEXT DEFAULT (datetime('now'))
        );
        """)


# --- news ---

def save_news_items(items: list[dict], cycle_id: str) -> None:
    with _conn() as con:
        for item in items:
            con.execute(
                "INSERT OR IGNORE INTO news_items (url, title, source, published_at, raw_text, cycle_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (item["url"], item["title"], item["source"],
                 item["published_at"], item["raw_text"], cycle_id),
            )


# --- sentiment ---

def save_sentiment(cycle_id: str, scores: dict[str, float], mentions: dict[str, list[str]]) -> None:
    with _conn() as con:
        for symbol, score in scores.items():
            con.execute(
                "INSERT INTO sentiment_history (cycle_id, symbol, score, headlines) VALUES (?, ?, ?, ?)",
                (cycle_id, symbol, score, json.dumps(mentions.get(symbol, []))),
            )


# --- signals ---

def save_signals(cycle_id: str, signals: list[dict], validated: bool = False) -> None:
    with _conn() as con:
        for s in signals:
            con.execute(
                "INSERT INTO signals (cycle_id, symbol, action, confidence, amount_eur, reason, "
                "sentiment, price_eur, validated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cycle_id, s["symbol"], s["action"], s["confidence"], s["amount_eur"],
                 s["reason"], s["sentiment_score"], s["price_eur"], int(validated)),
            )


# --- orders ---

def save_orders(cycle_id: str, orders: list[dict]) -> None:
    with _conn() as con:
        for o in orders:
            con.execute(
                "INSERT INTO orders (order_id, cycle_id, symbol, action, amount_eur, price_eur, status, mode) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (o["order_id"], cycle_id, o["symbol"], o["action"],
                 o["amount_eur"], o["price_eur"], o["status"], o["mode"]),
            )


# --- portfolio ---

def save_portfolio_snapshot(cycle_id: str, portfolio: dict) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO portfolio_snapshots (cycle_id, total_value_eur, cash_eur, risk_score, risk_label, positions_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cycle_id, portfolio["total_value_eur"], portfolio["cash_eur"],
             portfolio["risk_score"], portfolio["risk_label"],
             json.dumps(portfolio["positions"])),
        )


def load_latest_portfolio() -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM portfolio_snapshots ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["positions"] = json.loads(d["positions_json"])
    return d


def get_portfolio_history(limit: int = 48) -> list[dict]:
    """Return last N portfolio snapshots for P&L chart."""
    with _conn() as con:
        rows = con.execute(
            "SELECT created_at, total_value_eur, cash_eur, risk_score, risk_label "
            "FROM portfolio_snapshots ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_recent_news(limit: int = 30) -> list[dict]:
    """Return most recent news items."""
    with _conn() as con:
        rows = con.execute(
            "SELECT title, source, url, published_at, created_at "
            "FROM news_items ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest_sentiment() -> list[dict]:
    """Return latest sentiment score per asset (one row per symbol)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT symbol, score, headlines, created_at "
            "FROM sentiment_history "
            "WHERE created_at = (SELECT MAX(created_at) FROM sentiment_history s2 WHERE s2.symbol = sentiment_history.symbol) "
            "ORDER BY ABS(score) DESC",
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["headlines"] = json.loads(d["headlines"])
        result.append(d)
    return result


def get_recent_orders(limit: int = 50) -> list[dict]:
    """Return recent orders."""
    with _conn() as con:
        rows = con.execute(
            "SELECT order_id, created_at, symbol, action, amount_eur, price_eur, status, mode "
            "FROM orders ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_signals(limit: int = 50) -> list[dict]:
    """Return recent validated signals."""
    with _conn() as con:
        rows = con.execute(
            "SELECT created_at, symbol, action, confidence, amount_eur, reason, sentiment, validated "
            "FROM signals ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# --- forecasts ---

def save_forecasts(cycle_id: str, forecasts: list[dict]) -> None:
    with _conn() as con:
        for f in forecasts:
            con.execute(
                "INSERT INTO forecasts "
                "(cycle_id, symbol, forecast_score, direction, confidence, horizon, reasoning, sentiment_score, tech_score) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cycle_id, f["symbol"], f["forecast_score"], f["direction"],
                 f["confidence"], f["horizon"], f["reasoning"],
                 f["sentiment_score"], f["tech_score"]),
            )


def get_latest_forecasts() -> list[dict]:
    """Return most recent forecast per symbol."""
    with _conn() as con:
        rows = con.execute(
            "SELECT symbol, forecast_score, direction, confidence, horizon, reasoning, "
            "sentiment_score, tech_score, created_at "
            "FROM forecasts "
            "WHERE created_at = (SELECT MAX(f2.created_at) FROM forecasts f2 WHERE f2.symbol = forecasts.symbol) "
            "ORDER BY ABS(forecast_score) DESC",
        ).fetchall()
    return [dict(r) for r in rows]
