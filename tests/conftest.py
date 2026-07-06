"""Test environment — must run before any `core.config` import."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_TMP = tempfile.mkdtemp(prefix="revbot-test-")

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ["TRADING_MODE"] = "paper"
os.environ["DATA_DIR"] = _TMP
os.environ["DB_PATH"] = os.path.join(_TMP, "bot.sqlite")
os.environ["ASSETS"] = "BTC-USD,VOO"

import pytest  # noqa: E402

from core.db import _conn, init_db  # noqa: E402


@pytest.fixture()
def clean_db():
    """Fresh DB tables for tests that touch orders/fills."""
    init_db()
    with _conn() as con:
        con.execute("DELETE FROM orders")
        con.execute("DELETE FROM fills")
        con.execute("DELETE FROM signals")
    yield
