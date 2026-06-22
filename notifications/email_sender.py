"""
Constitutional Email Sender — single SMTP client for ALL emails.
Uses Gmail SMTP with STARTTLS (port 587).
Credentials: EMAIL_USER / EMAIL_PASS environment variables.
Retry: 3 attempts with exponential backoff (0 s, 2 s, 4 s).
Logs every attempt to notification_delivery.db.
"""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .retry import with_retry
from .delivery_store import record_attempt, record_success, record_failure

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587
_ATTEMPTS  = 3


def send(
    *,
    subject: str,
    html: str,
    to: str | None = None,
    sender: str | None = None,
    password: str | None = None,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
) -> bool:
    """
    Send an HTML email.

    Args:
        subject: Email subject line.
        html:    HTML body.
        to:      Recipient address. Defaults to EMAIL_USER env var.
        sender:  Sender address. Defaults to EMAIL_USER env var.
        password: SMTP password. Defaults to EMAIL_PASS env var.
        smtp_host: SMTP host. Defaults to smtp.gmail.com.
        smtp_port: SMTP port. Defaults to 587.

    Returns:
        True on success, False on failure.
    """
    _sender   = sender   or os.getenv("EMAIL_USER", "")
    _password = password or os.getenv("EMAIL_PASS", "")
    _to       = to       or os.getenv("EMAIL_USER", "")
    _host     = smtp_host or os.getenv("SMTP_HOST", _SMTP_HOST)
    _port     = smtp_port or int(os.getenv("SMTP_PORT", str(_SMTP_PORT)))

    if not _sender or not _password:
        print("[email_sender] EMAIL_USER / EMAIL_PASS not set — skipping.")
        return False

    rid = record_attempt("email", recipient=_to, subject=subject[:200])

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = _sender
    msg["To"]      = _to
    msg.attach(MIMEText(html, "html", "utf-8"))
    raw = msg.as_string()

    attempt = 0

    def _do_send():
        nonlocal attempt
        attempt += 1
        with smtplib.SMTP(_host, _port, timeout=30) as srv:
            srv.set_debuglevel(1)   # prints SMTP dialog (220, 250, MAIL FROM, RCPT TO, etc.)
            srv.ehlo()
            srv.starttls()
            srv.ehlo()
            srv.login(_sender, _password)
            srv.sendmail(_sender, _to, raw)
            print(f"[email_sender] SMTP MAIL FROM:<{_sender}>")
            print(f"[email_sender] SMTP RCPT TO:<{_to}>")
            print(f"[email_sender] SMTP Message-ID: {msg.get('Message-ID', 'auto-generated')}")

    try:
        with_retry(_do_send, attempts=_ATTEMPTS)
        record_success(rid, retry_count=attempt - 1)
        print(f"[email_sender] Sent → {_to} | {subject[:60]}")
        return True
    except Exception as e:
        record_failure(rid, str(e), retry_count=attempt - 1)
        print(f"[email_sender] FAILED after {attempt} attempt(s): {e}")
        return False
