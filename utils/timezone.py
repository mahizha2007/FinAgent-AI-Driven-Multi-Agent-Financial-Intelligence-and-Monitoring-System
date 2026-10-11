from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    """Return the current time in IST."""
    return datetime.now(IST)


def now_ist_iso() -> str:
    """Return the current time in IST ISO format."""
    return now_ist().isoformat(timespec="seconds")


def to_ist_timestamp(value) -> datetime | None:
    """Convert a timestamp-like value to an IST datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        current = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            current = datetime.fromisoformat(text)
        except ValueError:
            try:
                current = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
    if current.tzinfo is None:
        current = current.replace(tzinfo=IST)
    return current.astimezone(IST)
