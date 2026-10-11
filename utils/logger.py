from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from utils.connection import get_mysql_connection, initialize_mysql_schema
from utils.timezone import now_ist_iso


def get_logger(name: str = "financial_monitor") -> logging.Logger:
    """Create or return the shared application logger."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "system.log")
    handler.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


_MYSQL_LOG_CONNECTION = None
_MYSQL_LOG_DISABLED = False


def _get_mysql_log_connection():
    """Return a reusable MySQL connection for structured event mirroring."""
    global _MYSQL_LOG_CONNECTION, _MYSQL_LOG_DISABLED
    if _MYSQL_LOG_DISABLED:
        return None
    if _MYSQL_LOG_CONNECTION is not None:
        try:
            if _MYSQL_LOG_CONNECTION.is_connected():
                return _MYSQL_LOG_CONNECTION
        except Exception:
            _MYSQL_LOG_CONNECTION = None

    try:
        _MYSQL_LOG_CONNECTION = get_mysql_connection()
        if _MYSQL_LOG_CONNECTION is None:
            _MYSQL_LOG_DISABLED = True
            return None
        initialize_mysql_schema(_MYSQL_LOG_CONNECTION)
        return _MYSQL_LOG_CONNECTION
    except Exception:
        _MYSQL_LOG_CONNECTION = None
        _MYSQL_LOG_DISABLED = True
        return None


def log_event(user: str, action: str, data: Any, level: str = "INFO") -> None:
    """Write a structured event log entry to logs/app_events.jsonl."""
    logger = get_logger()
    payload = {
        "timestamp": now_ist_iso(),
        "user": user,
        "action": action,
        "message": data if isinstance(data, str) else json.dumps(data, default=str),
        "level": level.upper(),
    }
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app_events.jsonl"
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(payload, default=str) + "\n")
    log_method = getattr(logger, payload["level"].lower(), logger.info)
    log_method("%s | %s | %s | %s", payload["timestamp"], user, action, payload["message"])

    connection = _get_mysql_log_connection()
    if connection is None:
        return
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO logs (event_time, user_name, action, message)
            VALUES (%s, %s, %s, %s)
            """,
            (
                payload["timestamp"].replace("T", " ").replace("+05:30", ""),
                payload["user"],
                payload["action"],
                payload["message"],
            ),
        )
        connection.commit()
        cursor.close()
    except Exception:
        global _MYSQL_LOG_CONNECTION, _MYSQL_LOG_DISABLED
        _MYSQL_LOG_CONNECTION = None
        _MYSQL_LOG_DISABLED = True


def read_event_logs() -> list[dict[str, Any]]:
    """Read structured log events for the log viewer UI."""
    log_path = Path("logs") / "app_events.jsonl"
    if not log_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as log_file:
        for line in log_file:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries
