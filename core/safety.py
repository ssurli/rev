"""Safety controls — kill-switch, drawdown circuit-breaker, live-mode gates.

Priority: capital survival > returns.

- Kill-switch: file `data/KILL` (or env KILL_SWITCH=1) → bot skips the whole
  cycle. Removed manually when you want to resume.
- Circuit-breaker: if equity drops more than MAX_DRAWDOWN_HALT_PCT below the
  persisted high-water mark, the bot goes "flat & halt": file `data/HALT` is
  created and no order is placed until you delete it manually
  (`python -m core.safety --unlock`).
- Live gates: LIVE mode requires double confirmation (CLI flag AND env var
  LIVE_TRADING_CONFIRM=YES) plus an equity hard-cap (LIVE_MAX_CAPITAL_EUR).

All state files are chmod 0600.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from core import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Kill-switch
# ---------------------------------------------------------------------------

def kill_switch_active() -> bool:
    """True if the global kill-switch is on (file flag or env var)."""
    if os.getenv("KILL_SWITCH", "").lower() in ("1", "true", "yes"):
        return True
    return config.KILL_SWITCH_FILE.exists()


# ---------------------------------------------------------------------------
# Halt (circuit-breaker output) — requires manual unlock
# ---------------------------------------------------------------------------

def halt_active() -> bool:
    return config.HALT_FILE.exists()


def activate_halt(reason: str) -> None:
    """Create the HALT flag file. The bot stays flat until manual unlock."""
    config.HALT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "halted_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    }
    config.HALT_FILE.write_text(json.dumps(payload, indent=2))
    os.chmod(config.HALT_FILE, 0o600)
    logger.critical("CIRCUIT-BREAKER: halt activated — %s", reason)


def halt_info() -> dict | None:
    if not halt_active():
        return None
    try:
        return json.loads(config.HALT_FILE.read_text())
    except Exception:
        return {"reason": "unknown (unreadable HALT file)"}


def clear_halt() -> bool:
    """Manual unlock: delete the HALT file. Returns True if it was removed."""
    if config.HALT_FILE.exists():
        config.HALT_FILE.unlink()
        logger.warning("Halt cleared manually — trading re-enabled")
        return True
    return False


# ---------------------------------------------------------------------------
# High-water mark / drawdown circuit-breaker
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    try:
        return json.loads(config.SAFETY_STATE_PATH.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    config.SAFETY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.SAFETY_STATE_PATH.write_text(json.dumps(state, indent=2))
    os.chmod(config.SAFETY_STATE_PATH, 0o600)


def check_drawdown(equity_eur: float) -> tuple[bool, float]:
    """Update the high-water mark and evaluate the circuit-breaker.

    Returns (halted, drawdown_pct). If drawdown exceeds
    MAX_DRAWDOWN_HALT_PCT, the HALT file is created (flat & halt).
    Equity ≤ 0 is ignored (no data / API failure — don't poison the HWM).
    """
    if equity_eur <= 0:
        return halt_active(), 0.0

    state = _load_state()
    hwm = float(state.get("high_water_mark_eur", 0.0))

    if equity_eur > hwm:
        hwm = equity_eur
        state["high_water_mark_eur"] = hwm
        state["hwm_updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)
        return halt_active(), 0.0

    drawdown_pct = (hwm - equity_eur) / hwm * 100.0 if hwm > 0 else 0.0

    if drawdown_pct >= config.MAX_DRAWDOWN_HALT_PCT and not halt_active():
        activate_halt(
            f"Drawdown {drawdown_pct:.1f}% >= {config.MAX_DRAWDOWN_HALT_PCT:.1f}% "
            f"(equity €{equity_eur:.2f}, HWM €{hwm:.2f})"
        )

    return halt_active(), round(drawdown_pct, 2)


# ---------------------------------------------------------------------------
# Live-mode gates
# ---------------------------------------------------------------------------

def live_trading_allowed(equity_eur: float, cli_confirm: bool) -> tuple[bool, str]:
    """Double confirmation + hard-cap check for LIVE mode."""
    if not cli_confirm:
        return False, "LIVE richiede il flag --confirm-live (prima conferma)"
    if config.LIVE_TRADING_CONFIRM != "YES":
        return False, "LIVE richiede LIVE_TRADING_CONFIRM=YES nell'ambiente (seconda conferma)"
    if equity_eur > config.LIVE_MAX_CAPITAL_EUR:
        return False, (
            f"Equity €{equity_eur:.2f} oltre l'hard-cap LIVE_MAX_CAPITAL_EUR="
            f"€{config.LIVE_MAX_CAPITAL_EUR:.2f}"
        )
    return True, "ok"


# ---------------------------------------------------------------------------
# CLI: python -m core.safety --unlock | --status | --kill | --resume
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Safety controls")
    parser.add_argument("--unlock", action="store_true", help="Clear the HALT flag (manual unlock)")
    parser.add_argument("--kill", action="store_true", help="Activate the kill-switch")
    parser.add_argument("--resume", action="store_true", help="Remove the kill-switch file")
    parser.add_argument("--status", action="store_true", help="Show safety status")
    args = parser.parse_args()

    if args.unlock:
        print("HALT rimosso" if clear_halt() else "Nessun HALT attivo")
    elif args.kill:
        config.KILL_SWITCH_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.KILL_SWITCH_FILE.write_text(datetime.now(timezone.utc).isoformat())
        os.chmod(config.KILL_SWITCH_FILE, 0o600)
        print(f"Kill-switch attivato: {config.KILL_SWITCH_FILE}")
    elif args.resume:
        if config.KILL_SWITCH_FILE.exists():
            config.KILL_SWITCH_FILE.unlink()
            print("Kill-switch rimosso")
        else:
            print("Kill-switch non attivo")
    else:
        st = _load_state()
        print(f"Kill-switch : {'ATTIVO' if kill_switch_active() else 'off'}")
        print(f"Halt        : {'ATTIVO — ' + str(halt_info()) if halt_active() else 'off'}")
        print(f"HWM         : €{st.get('high_water_mark_eur', 0.0):.2f}")
