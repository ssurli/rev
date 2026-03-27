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
