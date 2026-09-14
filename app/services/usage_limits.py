"""
Usage limits that keep the public demo inside free-tier quotas.

- Daily counters (global LLM calls, per-user actions) live in the database so they survive restarts.
- Signup throttling is per client IP and kept in memory.
"""
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import Request

from app.database.models import SessionLocal, UsageCounter, User
from app.utils.config import USER_DAILY_ACTION_LIMIT, SIGNUPS_PER_IP_PER_HOUR


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


def client_ip(request: Request) -> str:
    """
    The Streamlit frontend calls the API from its own server, so requests arrive from localhost.
    It forwards the visitor's IP in X-Client-IP, which is trusted only on loopback connections.
    """
    peer = request.client.host if request.client else ""
    if peer in ("127.0.0.1", "::1", "localhost"):
        return request.headers.get("X-Client-IP") or peer
    return peer


_signups = defaultdict(deque)
_signup_lock = threading.Lock()


def limit_signups(request: Request):
    ip = client_ip(request)
    now = time.monotonic()
    with _signup_lock:
        window = _signups[ip]
        while window and now - window[0] > 3600:
            window.popleft()
        if len(window) >= SIGNUPS_PER_IP_PER_HOUR:
            raise LimitExceeded("Too many sign-ups from your network. Please try again in an hour.")
        window.append(now)
