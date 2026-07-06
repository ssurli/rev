"""Email alerts via SMTP (Zimbra o qualunque server SMTP con STARTTLS).

Eventi notificati: ordine eseguito, stop colpito, circuit-breaker attivato,
errore API. Disabilitato se SMTP_HOST è vuoto — il bot non si ferma mai
per un problema di notifica.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from core import config

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    return bool(config.SMTP_HOST and config.ALERT_EMAIL_TO)


def send_alert(subject: str, body: str) -> bool:
    """Send an email alert. Returns True on success, never raises."""
    if not is_enabled():
        logger.debug("Notifier disabled — skipped alert: %s", subject)
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"[rev-bot] {subject}"
        msg["From"] = config.ALERT_EMAIL_FROM
        msg["To"] = config.ALERT_EMAIL_TO

        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
        logger.info("Alert email sent: %s", subject)
        return True
    except Exception as exc:
        logger.error("Notifier failed (%s): %s", subject, exc)
        return False


# --- event helpers -----------------------------------------------------------

def notify_order(order: dict) -> None:
    send_alert(
        f"Ordine {order.get('action')} {order.get('symbol')}",
        f"Ordine eseguito:\n"
        f"  {order.get('action')} {order.get('symbol')} €{order.get('amount_eur', 0):.2f}\n"
        f"  status: {order.get('status')}  broker: {order.get('broker')}\n"
        f"  order_id: {order.get('order_id')}",
    )


def notify_stop_hit(symbol: str, reason: str) -> None:
    send_alert(f"STOP colpito — {symbol}", f"Stop-loss eseguito su {symbol}.\n{reason}")


def notify_circuit_breaker(reason: str) -> None:
    send_alert(
        "CIRCUIT-BREAKER ATTIVATO",
        f"Il bot è in flat & halt.\n{reason}\n\n"
        f"Sblocco manuale: python -m core.safety --unlock",
    )


def notify_error(context: str, error: str) -> None:
    send_alert(f"Errore API — {context}", f"{context}\n\n{error}")
