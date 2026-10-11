from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def send_email_alert(
    subject: str,
    body: str,
    recipients: list[str],
    severity: str,
    config: dict[str, str] | None = None,
) -> bool:
    """Send an email alert when SMTP environment variables are configured."""
    config = config or {}
    host = config.get("smtp_host") or os.getenv("ALERT_SMTP_HOST")
    port = int(config.get("smtp_port") or os.getenv("ALERT_SMTP_PORT", "587"))
    username = config.get("smtp_username") or os.getenv("ALERT_SMTP_USERNAME")
    password = config.get("smtp_password") or os.getenv("ALERT_SMTP_PASSWORD")
    sender = config.get("from_email") or os.getenv("ALERT_FROM_EMAIL", username or "")

    if not host or not sender or not recipients:
        return False

    message = EmailMessage()
    message["Subject"] = f"[{severity}] {subject}"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
        return True
    except Exception:
        return False
