"""
Constitutional Telegram Sender — single HTTP client for ALL Telegram messages.
Uses Telegram Bot API (sendMessage).
Credentials: TELEGRAM_TOKEN / TELEGRAM_CHAT_ID environment variables.
Retry: 3 attempts with exponential backoff (0 s, 2 s, 4 s).
Chunking: messages > 4000 chars split automatically.
Logs every attempt to notification_delivery.db.
"""
from __future__ import annotations

import os

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

from .retry import with_retry
from .delivery_store import record_attempt, record_success, record_failure

_API_BASE  = "https://api.telegram.org"
_MAX_CHARS = 4000
_ATTEMPTS  = 3


def _chunk(text: str) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > _MAX_CHARS:
            chunks.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        chunks.append(current)
    return chunks or [text]


def send(
    text: str,
    *,
    token: str | None = None,
    chat_id: str | None = None,
    parse_mode: str = "Markdown",
    subject: str = "",
) -> bool:
    """
    Send a Telegram message (chunked if > 4000 chars).

    Args:
        text:       Message text (Markdown supported).
        token:      Bot token. Defaults to TELEGRAM_TOKEN env var.
        chat_id:    Chat ID. Defaults to TELEGRAM_CHAT_ID env var.
        parse_mode: 'Markdown' or 'HTML'. Default 'Markdown'.
        subject:    Optional label for delivery log.

    Returns:
        True if all chunks sent successfully, False otherwise.
    """
    if not _HAS_REQUESTS:
        print("[telegram_sender] requests not installed — cannot send.")
        return False

    _token   = token   or os.getenv("TELEGRAM_TOKEN", "")
    _chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

    if not _token or not _chat_id:
        print("[telegram_sender] TELEGRAM_TOKEN / TELEGRAM_CHAT_ID not set — skipping.")
        return False

    url    = f"{_API_BASE}/bot{_token}/sendMessage"
    chunks = _chunk(text)
    all_ok = True

    for i, chunk in enumerate(chunks):
        rid     = record_attempt("telegram", recipient=_chat_id, subject=subject or text[:80])
        attempt = 0

        def _do_send(c=chunk):
            nonlocal attempt
            attempt += 1
            resp = _requests.post(
                url,
                json={"chat_id": _chat_id, "text": c, "parse_mode": parse_mode},
                timeout=10,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            return resp

        try:
            with_retry(_do_send, attempts=_ATTEMPTS)
            record_success(rid, retry_count=attempt - 1)
            print(f"[telegram_sender] chunk {i+1}/{len(chunks)} sent ({len(chunk)} chars)")
        except Exception as e:
            record_failure(rid, str(e), retry_count=attempt - 1)
            print(f"[telegram_sender] chunk {i+1}/{len(chunks)} FAILED after {attempt} attempt(s): {e}")
            all_ok = False

    return all_ok
