"""
SQLite (via SQLModel) stores naive datetimes, so the app is consistent
about using naive-UTC everywhere rather than mixing naive and
timezone-aware values, which would break comparisons. This wraps the
non-deprecated way of getting that.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
