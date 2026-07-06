"""Structured JSON decision log — one line per decision, append-only.

Every accept/reject (including cost-gate and overtrading blocks) is logged
to data/decisions.jsonl so any order — or non-order — can be audited later.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from core import config

logger = logging.getLogger(__name__)


def log_decision(
    cycle_id: str,
    symbol: str,
    action: str,
    decision: str,          # "accepted" | "rejected" | "halted" | "info"
    reason: str,
    context: dict | None = None,
) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "cycle_id": cycle_id,
        "symbol": symbol,
        "action": action,
        "decision": decision,
        "reason": reason,
        "context": context or {},
    }
    try:
        path = config.DECISIONS_LOG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists()
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        if is_new:
            os.chmod(path, 0o600)
    except Exception as exc:  # logging must never break the cycle
        logger.warning("decision_log write failed: %s", exc)
