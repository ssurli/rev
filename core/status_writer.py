"""Writes data/status.json after every cycle — the read-only feed for the
mobile dashboard (ui/monitor.html). The UI never talks to broker or DB.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from core import config, safety
from core.db import get_portfolio_history, get_recent_orders, get_recent_signals

logger = logging.getLogger(__name__)


def write_status(state: dict) -> None:
    try:
        portfolio = state.get("portfolio", {}) or {}
        equity = float(portfolio.get("total_value_eur", 0.0))
        _, drawdown_pct = safety.check_drawdown(equity) if equity > 0 else (False, 0.0)

        status = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": state.get("mode", "paper"),
            "cycle_id": state.get("cycle_id", ""),
            "kill_switch": safety.kill_switch_active(),
            "halted": safety.halt_active(),
            "halt_info": safety.halt_info(),
            "drawdown_pct": drawdown_pct,
            "equity_eur": equity,
            "cash_eur": float(portfolio.get("cash_eur", 0.0)),
            "risk_score": portfolio.get("risk_score", 0),
            "risk_label": portfolio.get("risk_label", "-"),
            "positions": portfolio.get("positions", []),
            "equity_history": get_portfolio_history(limit=96),
            "last_orders": get_recent_orders(limit=20),
            "last_signals": [
                s for s in get_recent_signals(limit=30) if s.get("validated")
            ],
            "errors": state.get("errors", []),
        }

        path = config.STATUS_JSON_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(status, ensure_ascii=False, default=str))
        os.replace(tmp, path)
    except Exception as exc:  # status write must never break the cycle
        logger.warning("status_writer failed: %s", exc)
