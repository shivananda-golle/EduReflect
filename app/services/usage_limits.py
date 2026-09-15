"""
Usage limits that keep the public demo inside free-tier quotas.

- Daily counters (global LLM calls, per-user actions) live in the database so they survive restarts.
- Signup throttling is per client IP (or a shared hourly cap when the IP is unknown) and kept in memory.
"""
import ipaddress
import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

from fastapi import Request

from app.database.models import SessionLocal, UsageCounter, User
from app.utils.config import SIGNUPS_PER_HOUR_GLOBAL, SIGNUPS_PER_IP_PER_HOUR, USER_DAILY_ACTION_LIMIT

logger = logging.getLogger(__name__)


class LimitExceeded(Exception):
    """Raised when a usage limit is hit; returned to clients as HTTP 429 with a friendly message."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


_counter_lock = threading.Lock()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def consume(scope: str, limit: int, message: str) -> int:
    """Increment today's counter for `scope`, or raise LimitExceeded if it is already at `limit`."""
    with _counter_lock:
        db = SessionLocal()
        try:
            day = _today()
            row = db.get(UsageCounter, (scope, day))
            if row is None:
                row = UsageCounter(scope=scope, day=day, count=0)
                db.add(row)
            if row.count >= limit:
                raise LimitExceeded(message)
            row.count += 1
            db.commit()
            return row.count
        finally:
            db.close()


def used_today(scope: str) -> int:
    db = SessionLocal()
    try:
        row = db.get(UsageCounter, (scope, _today()))
        return row.count if row else 0
    finally:
        db.close()


def user_scope(user_id: str) -> str:
    return f"user:{user_id}"


def user_usage(user_id: str) -> dict:
    used = used_today(user_scope(user_id))
    return {
        "daily_limit": USER_DAILY_ACTION_LIMIT,
        "daily_used": used,
        "remaining_today": max(0, USER_DAILY_ACTION_LIMIT - used),
    }


def limit_user_action(current_user: User):
    """Count one LLM-backed action (question, quiz, summary, upload) against the user's daily limit."""
    consume(
        user_scope(current_user.id),
        USER_DAILY_ACTION_LIMIT,
        f"You've used all {USER_DAILY_ACTION_LIMIT} free actions for today. Please come back tomorrow.",
    )


def client_ip(request: Request) -> Optional[str]:
    """
    The visitor's public IP, or None if it can't be determined.

    The Streamlit frontend calls the API from its own server, so requests arrive from localhost; it forwards
    the visitor's IP in X-Client-IP, which is trusted only on loopback connections. Private or loopback
    addresses mean a proxy hid the visitor, so they don't identify anyone.
    """
    peer = request.client.host if request.client else ""
    candidate = request.headers.get("X-Client-IP", "") if peer in ("127.0.0.1", "::1", "localhost") else peer
    try:
        address = ipaddress.ip_address(candidate.strip())
    except ValueError:
        return None
    return None if address.is_private or address.is_loopback else str(address)


_signups = defaultdict(deque)
_signup_lock = threading.Lock()
_signup_mode_logged = False


def limit_signups(request: Request):
    """Per-IP sign-up limit when the visitor IP is known; otherwise a shared hourly cap so real visitors aren't blocked."""
    global _signup_mode_logged
    ip = client_ip(request)
    key, limit = (f"ip:{ip}", SIGNUPS_PER_IP_PER_HOUR) if ip else ("global", SIGNUPS_PER_HOUR_GLOBAL)
    if not _signup_mode_logged:
        logger.info("Sign-up limiting mode: %s", "per visitor IP" if ip else "shared hourly cap (visitor IP unavailable)")
        _signup_mode_logged = True

    now = time.monotonic()
    with _signup_lock:
        window = _signups[key]
        while window and now - window[0] > 3600:
            window.popleft()
        if len(window) >= limit:
            raise LimitExceeded("Too many sign-ups right now. Please try again in an hour.")
        window.append(now)
