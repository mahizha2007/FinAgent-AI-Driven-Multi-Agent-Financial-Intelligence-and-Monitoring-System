from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from services.access_control import AccessControl
from utils.auth import hash_password, validate_password_strength, validate_username, verify_password
from utils.connection import get_mysql_connection, initialize_mysql_schema
from utils.logger import log_event
from utils.timezone import now_ist, now_ist_iso, to_ist_timestamp


class DatabaseManager:
    """Database manager with SQLite default storage and optional MySQL mirroring."""

    def __init__(self, db_path: str = "data/financial_monitor.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.mysql_connection = get_mysql_connection()
        self.access_control = AccessControl()
        if self.mysql_connection:
            try:
                initialize_mysql_schema(self.mysql_connection)
            except Exception:
                self.mysql_connection = None
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tenants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_name TEXT UNIQUE NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            user_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            if "password_hash" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            if "role" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'viewer'")
            if "tenant_id" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN tenant_id INTEGER DEFAULT 1")
            if "is_active" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
            if "failed_login_count" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN failed_login_count INTEGER DEFAULT 0")
            if "locked_until" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN locked_until TEXT")
            if "last_login_at" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN last_login_at TEXT")
            if "last_failed_login_at" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN last_failed_login_at TEXT")
            if "password_updated_at" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN password_updated_at TEXT")
            connection.execute("UPDATE users SET role = COALESCE(role, 'viewer')")
            connection.execute("UPDATE users SET tenant_id = COALESCE(tenant_id, 1)")
            connection.execute("UPDATE users SET is_active = COALESCE(is_active, 1)")
            connection.execute("UPDATE users SET failed_login_count = COALESCE(failed_login_count, 0)")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS anomalies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT NOT NULL,
                    transaction_id TEXT NOT NULL,
                    anomaly_score REAL NOT NULL,
                    risk_level TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    explanation TEXT,
                    UNIQUE(event_time, transaction_id, decision)
                )
                """
            )
            anomaly_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(anomalies)").fetchall()
            }
            if "severity" not in anomaly_columns:
                connection.execute("ALTER TABLE anomalies ADD COLUMN severity TEXT DEFAULT 'INFO'")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    details TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    transaction_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    risk_probability REAL NOT NULL,
                    final_score REAL NOT NULL,
                    recommended_action TEXT NOT NULL,
                    reasoning_trace TEXT NOT NULL,
                    severity TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS model_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    model_name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    metadata TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    user_query TEXT NOT NULL,
                    response TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    user_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    message TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_acknowledgements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    anomaly_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    acknowledged_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(anomaly_id, username)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    username TEXT NOT NULL,
                    success INTEGER DEFAULT 0,
                    message TEXT,
                    remote_addr TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS shared_input_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    source_label TEXT,
                    username TEXT,
                    updated_at TEXT,
                    is_active INTEGER DEFAULT 0
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    tenant_id INTEGER DEFAULT 1,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'OPEN',
                    priority TEXT DEFAULT 'INFO',
                    owner TEXT,
                    source_transaction_id TEXT,
                    created_by TEXT,
                    workflow_state TEXT DEFAULT 'open'
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    tenant_id INTEGER DEFAULT 1,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    approver TEXT,
                    status TEXT DEFAULT 'PENDING',
                    comments TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_outputs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    tenant_id INTEGER DEFAULT 1,
                    agent_name TEXT NOT NULL,
                    transaction_id TEXT,
                    score REAL,
                    confidence REAL,
                    payload TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    tenant_id INTEGER DEFAULT 1,
                    interaction_key TEXT,
                    feedback TEXT,
                    notes TEXT
                )
                """
            )
            shared_state_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(shared_input_state)").fetchall()
            }
            if "tenant_id" not in shared_state_columns:
                connection.execute("ALTER TABLE shared_input_state ADD COLUMN tenant_id INTEGER DEFAULT 1")
            connection.commit()
        self.ensure_default_tenant()
        self.ensure_default_user()

    def log_anomaly(
        self,
        event_time: str,
        transaction_id: str,
        anomaly_score: float,
        risk_level: str,
        decision: str,
        explanation: str,
        severity: str = "INFO",
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO anomalies (event_time, transaction_id, anomaly_score, risk_level, decision, explanation, severity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_time, transaction_id, anomaly_score, risk_level, decision, explanation, severity),
            )
            connection.commit()
        self.save_log(
            "system",
            "anomaly_recorded",
            f"{transaction_id} | score={anomaly_score:.2f} | risk={risk_level} | decision={decision}",
        )

    def log_agent_decision(self, agent_name: str, decision: str, details: str) -> None:
        event_time = now_ist_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_decisions (event_time, agent_name, decision, details)
                VALUES (?, ?, ?, ?)
                """,
                (event_time, agent_name, decision, details),
            )
            connection.commit()
        self.save_log(agent_name, decision, details)

    def log_user_query(self, user_query: str, response: str) -> None:
        event_time = now_ist_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_history (event_time, user_query, response)
                VALUES (?, ?, ?)
                """,
                (event_time, user_query, response),
            )
            connection.commit()
        self.save_chat(user_query, response)

    def save_chat(self, user_query: str, response: str) -> None:
        """Mirror chat records to MySQL when configured."""
        if self.mysql_connection is None:
            return
        try:
            cursor = self.mysql_connection.cursor()
            cursor.execute(
                "INSERT INTO chat_history (user_query, response) VALUES (%s, %s)",
                (user_query, response),
            )
            self.mysql_connection.commit()
            cursor.close()
        except Exception:
            self.mysql_connection = None

    def save_log(self, user_name: str, action: str, message: str) -> None:
        """Persist structured logs locally and mirror through the shared logger."""
        event_time = now_ist_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO logs (event_time, user_name, action, message)
                VALUES (?, ?, ?, ?)
                """,
                (event_time, user_name, action, message),
            )
            connection.commit()

        log_event(user_name, action, message)

    def run_query(self, query: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]

    def log_decision(
        self,
        transaction_id: str,
        decision: str,
        confidence_score: float,
        risk_probability: float,
        final_score: float,
        recommended_action: str,
        reasoning_trace: str,
        severity: str,
    ) -> None:
        """Persist centralized decision-intelligence outputs."""
        event_time = now_ist_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO decisions (
                    event_time, transaction_id, decision, confidence_score, risk_probability, final_score,
                    recommended_action, reasoning_trace, severity
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_time,
                    transaction_id,
                    decision,
                    confidence_score,
                    risk_probability,
                    final_score,
                    recommended_action,
                    reasoning_trace,
                    severity,
                ),
            )
            connection.commit()

    def log_model_version(self, model_name: str, version: str, metadata: str) -> None:
        """Persist model version metadata for governance."""
        event_time = now_ist_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO model_versions (event_time, model_name, version, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (event_time, model_name, version, metadata),
            )
            connection.commit()

    def ensure_default_tenant(self) -> None:
        """Ensure a default tenant exists."""
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM tenants WHERE tenant_name = ?",
                ("Default Finance",),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO tenants (tenant_name) VALUES (?)",
                    ("Default Finance",),
                )
                connection.commit()

    def ensure_default_user(self) -> None:
        """Ensure a default local user exists for first-time access."""
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT username FROM users WHERE username = ?",
                ("admin",),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO users (
                        username, password_hash, role, tenant_id, is_active, failed_login_count, password_updated_at
                    ) VALUES (?, ?, ?, ?, 1, 0, ?)
                    """,
                    ("admin", hash_password("admin123"), "admin", 1, now_ist_iso()),
                )
                connection.commit()
            else:
                record = connection.execute(
                    "SELECT password_hash, role, tenant_id, is_active, password_updated_at FROM users WHERE username = ?",
                    ("admin",),
                ).fetchone()
                if record is not None and not record["password_hash"]:
                    connection.execute(
                        "UPDATE users SET password_hash = ? WHERE username = ?",
                        (hash_password("admin123"), "admin"),
                    )
                    connection.commit()
                if record is not None and (not record["role"] or record["tenant_id"] is None):
                    connection.execute(
                        "UPDATE users SET role = COALESCE(role, 'admin'), tenant_id = COALESCE(tenant_id, 1) WHERE username = ?",
                        ("admin",),
                    )
                    connection.commit()
                if record is not None and record["role"] != "admin":
                    connection.execute(
                        "UPDATE users SET role = 'admin', tenant_id = COALESCE(tenant_id, 1) WHERE username = ?",
                        ("admin",),
                    )
                    connection.commit()
                if record is not None and not record["is_active"]:
                    connection.execute(
                        "UPDATE users SET is_active = 1 WHERE username = ?",
                        ("admin",),
                    )
                    connection.commit()
                if record is not None and not record["password_updated_at"]:
                    connection.execute(
                        "UPDATE users SET password_updated_at = ? WHERE username = ?",
                        (now_ist_iso(), "admin"),
                    )
                    connection.commit()

    def create_user(
        self,
        username: str,
        password: str,
        role: str = "viewer",
        tenant_id: int = 1,
        created_by: str = "self-service",
        require_approval: bool = False,
    ) -> tuple[bool, str]:
        """Create a local user account with a validated role and password."""
        username = (username or "").strip()
        role = self.access_control.normalize_role(role)
        is_valid_username, username_message = validate_username(username)
        if not is_valid_username:
            return False, username_message
        is_valid_password, password_message = validate_password_strength(password, username=username)
        if not is_valid_password:
            return False, password_message
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT username FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if existing:
                return False, "That username already exists."
            connection.execute(
                """
                INSERT INTO users (
                    username, password_hash, role, tenant_id, is_active, failed_login_count, password_updated_at
                ) VALUES (?, ?, ?, ?, 1, 0, ?)
                """,
                (
                    username,
                    hash_password(password),
                    role,
                    int(tenant_id),
                    now_ist_iso(),
                ),
            )
            if require_approval:
                connection.execute(
                    """
                    UPDATE users
                    SET is_active = 0
                    WHERE username = ?
                    """,
                    (username,),
                )
            connection.commit()
        if require_approval:
            self.create_approval(
                tenant_id=int(tenant_id),
                entity_type="user_registration",
                entity_id=username,
                step_name="Admin Approval",
                approver="admin",
                status="PENDING",
                comments=f"Self-service registration awaiting admin approval for role {role}",
            )
            self.save_log(created_by, "register_pending_approval", f"{username} requested access with role {role}")
            return True, "Account created and submitted for admin approval."
        self.save_log(created_by, "register", f"Local account created for {username} with role {role}")
        return True, "Account created successfully."

    def get_user_profile(self, username: str) -> dict[str, Any]:
        """Return role and tenant metadata for a user."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                       u.username,
                       CASE WHEN u.username = 'admin' THEN 'admin' ELSE COALESCE(u.role, 'viewer') END AS role,
                       COALESCE(u.tenant_id, 1) AS tenant_id,
                       COALESCE(t.tenant_name, 'Default Finance') AS tenant_name
                FROM users u
                LEFT JOIN tenants t ON t.id = COALESCE(u.tenant_id, 1)
                WHERE u.username = ?
                """,
                (username.strip(),),
            ).fetchone()
        return dict(row) if row else {"username": username, "role": "viewer", "tenant_id": 1, "tenant_name": "Default Finance"}

    def authenticate_user(self, username: str, password: str) -> bool:
        """Check whether the supplied credentials are valid."""
        success, _ = self.authenticate_user_with_status(username, password)
        return success

    def authenticate_user_with_status(self, username: str, password: str) -> tuple[bool, str]:
        """Authenticate a user and return a user-friendly status message."""
        username = (username or "").strip()
        if not username or not (password or "").strip():
            return False, "Username and password are required."
        with self._connect() as connection:
            record = connection.execute(
                """
                SELECT password_hash, is_active, failed_login_count, locked_until
                FROM users
                WHERE username = ?
                """,
                (username,),
            ).fetchone()
        if record is None:
            self.record_login_attempt(username, False, "Invalid username or password.")
            return False, "Invalid username or password."
        if not int(record["is_active"] or 0):
            if self.has_pending_user_approval(username):
                self.record_login_attempt(username, False, "Account pending admin approval.")
                return False, "Your account is waiting for admin approval."
            self.record_login_attempt(username, False, "Account is deactivated.")
            return False, "This account is deactivated. Please contact an administrator."

        locked_until = to_ist_timestamp(record["locked_until"])
        if locked_until is not None and locked_until > now_ist():
            self.record_login_attempt(username, False, f"Account locked until {locked_until.strftime('%Y-%m-%d %H:%M:%S IST')}.")
            return False, f"Account locked until {locked_until.strftime('%Y-%m-%d %H:%M:%S IST')}."

        if verify_password(password, record["password_hash"]):
            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE users
                    SET failed_login_count = 0,
                        locked_until = NULL,
                        last_login_at = ?
                    WHERE username = ?
                    """,
                    (now_ist_iso(), username),
                )
                connection.commit()
            self.record_login_attempt(username, True, "Login successful.")
            self.save_log(username, "login", "Authenticated successfully")
            return True, "Login successful."

        failed_count = int(record["failed_login_count"] or 0) + 1
        lock_message = "Invalid username or password."
        if failed_count >= 5:
            locked_until_text = (now_ist() + timedelta(minutes=15)).replace(microsecond=0).isoformat(timespec="seconds")
            lock_message = "Too many failed attempts. Account locked for 15 minutes."
        else:
            locked_until_text = None
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE users
                SET failed_login_count = ?,
                    locked_until = ?,
                    last_failed_login_at = ?
                WHERE username = ?
                """,
                (failed_count, locked_until_text, now_ist_iso(), username),
            )
            connection.commit()
        self.record_login_attempt(username, False, lock_message)
        self.save_log(username, "login_failed", lock_message)
        return False, lock_message

    def record_login_attempt(self, username: str, success: bool, message: str, remote_addr: str = "streamlit-session") -> None:
        """Persist authentication attempts for audit and lockout analysis."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO login_attempts (event_time, username, success, message, remote_addr)
                VALUES (?, ?, ?, ?, ?)
                """,
                (now_ist_iso(), username or "unknown", 1 if success else 0, message, remote_addr),
            )
            connection.commit()
        log_event(
            username or "unknown",
            "login_attempt",
            {"success": bool(success), "message": message, "remote_addr": remote_addr},
            level="INFO" if success else "WARNING",
        )

    def list_users(self) -> list[dict[str, Any]]:
        """Return user access records for admin management screens."""
        return self.run_query(
            """
            SELECT
                u.username,
                CASE WHEN u.username = 'admin' THEN 'admin' ELSE COALESCE(u.role, 'viewer') END AS role,
                CASE WHEN u.username = 'admin' THEN 1 ELSE COALESCE(u.is_active, 1) END AS is_active,
                COALESCE(u.failed_login_count, 0) AS failed_login_count,
                u.locked_until,
                u.last_login_at,
                u.password_updated_at,
                COALESCE(u.tenant_id, 1) AS tenant_id,
                COALESCE(t.tenant_name, 'Default Finance') AS tenant_name,
                u.created_at
            FROM users u
            LEFT JOIN tenants t ON t.id = COALESCE(u.tenant_id, 1)
            ORDER BY CASE WHEN u.username = 'admin' THEN 0 ELSE 1 END, u.username
            """
        )

    def update_user_role(self, username: str, role: str, actor: str) -> tuple[bool, str]:
        """Update a user's role."""
        username = (username or "").strip()
        role = self.access_control.normalize_role(role)
        if username == "admin" and role != "admin":
            return False, "The default admin account must remain an administrator."
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT username FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if existing is None:
                return False, "User not found."
            connection.execute(
                "UPDATE users SET role = ? WHERE username = ?",
                (role, username),
            )
            connection.commit()
        self.save_log(actor, "update_user_role", f"{username} -> {role}")
        return True, "User role updated."

    def set_user_active(self, username: str, is_active: bool, actor: str) -> tuple[bool, str]:
        """Activate or deactivate a user account."""
        username = (username or "").strip()
        if username == "admin" and not is_active:
            return False, "The default admin account cannot be deactivated."
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT username FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if existing is None:
                return False, "User not found."
            connection.execute(
                """
                UPDATE users
                SET is_active = ?,
                    failed_login_count = CASE WHEN ? = 1 THEN 0 ELSE failed_login_count END,
                    locked_until = CASE WHEN ? = 1 THEN NULL ELSE locked_until END
                WHERE username = ?
                """,
                (1 if is_active else 0, 1 if is_active else 0, 1 if is_active else 0, username),
            )
            connection.commit()
        self.save_log(actor, "set_user_active", f"{username} -> {'active' if is_active else 'inactive'}")
        return True, "User status updated."

    def unlock_user(self, username: str, actor: str) -> tuple[bool, str]:
        """Clear lockout state for a user."""
        username = (username or "").strip()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT username FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if existing is None:
                return False, "User not found."
            connection.execute(
                """
                UPDATE users
                SET failed_login_count = 0,
                    locked_until = NULL
                WHERE username = ?
                """,
                (username,),
            )
            connection.commit()
        self.save_log(actor, "unlock_user", username)
        return True, "User unlocked."

    def get_login_attempts(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent authentication attempts for security monitoring."""
        return self.run_query(
            f"""
            SELECT event_time, username, success, message, remote_addr
            FROM login_attempts
            ORDER BY id DESC
            LIMIT {int(limit)}
            """
        )

    def has_pending_user_approval(self, username: str) -> bool:
        """Return whether a user has a pending registration approval."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id
                FROM approvals
                WHERE entity_type = 'user_registration'
                  AND entity_id = ?
                  AND status = 'PENDING'
                ORDER BY id DESC
                LIMIT 1
                """,
                ((username or "").strip(),),
            ).fetchone()
        return row is not None

    def get_pending_user_approvals(self, tenant_id: int = 1) -> list[dict[str, Any]]:
        """Return pending self-service user approvals for admin review."""
        return self.run_query(
            f"""
            SELECT
                a.event_time,
                a.entity_id AS username,
                a.step_name,
                a.status,
                a.comments,
                COALESCE(u.role, 'viewer') AS requested_role,
                COALESCE(u.tenant_id, 1) AS tenant_id,
                COALESCE(u.is_active, 0) AS is_active,
                COALESCE(u.created_at, a.event_time) AS created_at
            FROM approvals a
            LEFT JOIN users u ON u.username = a.entity_id
            WHERE a.entity_type = 'user_registration'
              AND a.status = 'PENDING'
              AND COALESCE(u.tenant_id, 1) = {int(tenant_id)}
            ORDER BY a.id DESC
            """
        )

    def resolve_user_registration(self, username: str, approved: bool, actor: str) -> tuple[bool, str]:
        """Approve or reject a pending self-service registration."""
        username = (username or "").strip()
        status = "APPROVED" if approved else "REJECTED"
        with self._connect() as connection:
            user = connection.execute(
                "SELECT username FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if user is None:
                return False, "User not found."
            pending = connection.execute(
                """
                SELECT id
                FROM approvals
                WHERE entity_type = 'user_registration'
                  AND entity_id = ?
                  AND status = 'PENDING'
                ORDER BY id DESC
                LIMIT 1
                """,
                (username,),
            ).fetchone()
            if pending is None:
                return False, "No pending approval exists for that user."
            connection.execute(
                """
                UPDATE approvals
                SET status = ?, comments = ?
                WHERE id = ?
                """,
                (
                    status,
                    f"{status.title()} by {actor} at {now_ist_iso()}",
                    pending["id"],
                ),
            )
            connection.execute(
                """
                UPDATE users
                SET is_active = ?,
                    failed_login_count = 0,
                    locked_until = NULL
                WHERE username = ?
                """,
                (1 if approved else 0, username),
            )
            connection.commit()
        self.save_log(actor, "user_registration_resolved", f"{username} -> {status}")
        return True, f"User {username} {status.lower()}."

    def save_shared_input(self, df: pd.DataFrame, source_label: str, username: str) -> None:
        """Persist the latest submitted dataset so the dashboard can pick it up."""
        shared_path = Path("data/shared_input.csv")
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(shared_path, index=False)
        updated_at = now_ist_iso()
        tenant_id = int(self.get_user_profile(username).get("tenant_id", 1))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO shared_input_state (id, source_label, username, updated_at, is_active, tenant_id)
                VALUES (1, ?, ?, ?, 1, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_label = excluded.source_label,
                    username = excluded.username,
                    updated_at = excluded.updated_at,
                    is_active = excluded.is_active,
                    tenant_id = excluded.tenant_id
                """,
                (source_label, username, updated_at, tenant_id),
            )
            connection.commit()
        mysql_source_label = f"{source_label} | {updated_at}"
        self.sync_dataset_to_mysql(df, mysql_source_label, username, tenant_id, replace_existing=False)
        self.save_log(username, "shared_input_saved", f"{source_label} at {updated_at}")

    def sync_dataset_to_mysql(
        self,
        df: pd.DataFrame,
        source_label: str,
        username: str,
        tenant_id: int = 1,
        replace_existing: bool = True,
    ) -> int:
        """Mirror a dataset into MySQL and return the number of inserted rows."""
        if self.mysql_connection is None:
            return 0
        try:
            normalized = df.copy()
            if "date" in normalized.columns:
                normalized.loc[:, "date"] = pd.to_datetime(normalized["date"], errors="coerce")
            column_aliases = {
                "receivables": "accounts_receivable",
                "customer_count": "customer_count",
                "customers": "customer_count",
                "marketing": "marketing_spend",
            }
            for source_column, target_column in column_aliases.items():
                if source_column in normalized.columns and target_column not in normalized.columns:
                    normalized[target_column] = normalized[source_column]
            optional_columns = [
                "revenue",
                "expenses",
                "cash_flow",
                "customer_count",
                "accounts_receivable",
                "inventory",
                "marketing_spend",
                "outstanding_amount",
            ]
            for column in optional_columns:
                if column not in normalized.columns:
                    normalized[column] = 0.0
                normalized.loc[:, column] = pd.to_numeric(normalized[column], errors="coerce").fillna(0.0)
            if "payment_status" not in normalized.columns:
                normalized["payment_status"] = ""
            else:
                normalized.loc[:, "payment_status"] = normalized["payment_status"].fillna("").astype(str)
            if "transaction_id" not in normalized.columns:
                normalized["transaction_id"] = [f"{source_label.upper()}-{index + 1:04d}" for index in range(len(normalized))]
            else:
                normalized.loc[:, "transaction_id"] = normalized["transaction_id"].fillna("").astype(str)

            cursor = self.mysql_connection.cursor()
            if replace_existing:
                cursor.execute(
                    """
                    DELETE FROM ingested_financial_data
                    WHERE username = %s AND tenant_id = %s AND source_label = %s
                    """,
                    (username, int(tenant_id), source_label),
                )
            insert_sql = """
                INSERT INTO ingested_financial_data (
                    source_label, username, tenant_id, record_date, transaction_id, revenue, expenses, cash_flow,
                    customer_count, accounts_receivable, inventory, marketing_spend, payment_status, outstanding_amount
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            rows = []
            for record in normalized.to_dict(orient="records"):
                record_date = pd.to_datetime(record.get("date"), errors="coerce")
                rows.append(
                    (
                        source_label,
                        username,
                        int(tenant_id),
                        record_date.date() if pd.notna(record_date) else None,
                        str(record.get("transaction_id", "")),
                        float(record.get("revenue", 0.0) or 0.0),
                        float(record.get("expenses", 0.0) or 0.0),
                        float(record.get("cash_flow", 0.0) or 0.0),
                        float(record.get("customer_count", 0.0) or 0.0),
                        float(record.get("accounts_receivable", 0.0) or 0.0),
                        float(record.get("inventory", 0.0) or 0.0),
                        float(record.get("marketing_spend", 0.0) or 0.0),
                        str(record.get("payment_status", "") or ""),
                        float(record.get("outstanding_amount", 0.0) or 0.0),
                    )
                )
            if rows:
                cursor.executemany(insert_sql, rows)
            self.mysql_connection.commit()
            cursor.close()
            return len(rows)
        except Exception:
            self.mysql_connection = None
            return 0

    def get_shared_input_state(self, tenant_id: int = 1) -> dict[str, Any] | None:
        """Return the metadata for the active shared dataset."""
        rows = self.run_query(
            f"""
            SELECT source_label, username, updated_at, is_active
            FROM shared_input_state
            WHERE id = 1
            AND COALESCE(tenant_id, 1) = {int(tenant_id)}
            """
        )
        return rows[0] if rows else None

    def clear_shared_input(self, username: str) -> None:
        """Clear the active shared dataset flag and remove the cached file if present."""
        shared_path = Path("data/shared_input.csv")
        if shared_path.exists():
            shared_path.unlink()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO shared_input_state (id, source_label, username, updated_at, is_active)
                VALUES (1, '', ?, ?, 0)
                ON CONFLICT(id) DO UPDATE SET
                    source_label = '',
                    username = excluded.username,
                    updated_at = excluded.updated_at,
                    is_active = 0
                """,
                (username, now_ist_iso()),
            )
            connection.commit()
        self.save_log(username, "shared_input_cleared", "Shared dataset reset to default")

    def set_app_setting(self, key: str, value: str) -> None:
        """Persist a simple application setting."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO app_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            connection.commit()

    def get_app_setting(self, key: str, default: str = "") -> str:
        """Fetch a simple application setting."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
        return row["value"] if row and row["value"] is not None else default

    def save_email_alert_settings(self, settings: dict[str, str]) -> None:
        """Persist email alert configuration values."""
        for key, value in settings.items():
            self.set_app_setting(f"email_alert.{key}", value)

    def get_email_alert_settings(self) -> dict[str, str]:
        """Return stored email alert configuration."""
        keys = ["enabled", "smtp_host", "smtp_port", "smtp_username", "smtp_password", "from_email", "recipients"]
        return {key: self.get_app_setting(f"email_alert.{key}", "") for key in keys}

    def get_recent_memory(self, limit: int = 5) -> list[dict[str, Any]]:
        return self.run_query(
            f"""
            SELECT event_time, user_query, response
            FROM chat_history
            ORDER BY id DESC
            LIMIT {int(limit)}
            """
        )

    def get_logs(self, limit: int | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT event_time, user_name, action, message
            FROM logs
            ORDER BY id DESC
        """
        if limit is not None:
            query += f"\nLIMIT {int(limit)}"
        return self.run_query(query)

    def acknowledge_alert(self, anomaly_id: int, username: str) -> None:
        """Persist alert acknowledgement for a specific user."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO alert_acknowledgements (anomaly_id, username, acknowledged_at)
                VALUES (?, ?, ?)
                """,
                (int(anomaly_id), username.strip(), now_ist_iso()),
            )
            connection.commit()

    def get_unacknowledged_alerts(self, username: str, limit: int = 25) -> list[dict[str, Any]]:
        """Return alert anomalies not yet acknowledged by the given user."""
        safe_username = (username or "").strip()
        return self.run_query(
            f"""
            SELECT
                a.id AS anomaly_id,
                a.event_time,
                a.transaction_id,
                a.anomaly_score,
                a.risk_level,
                a.decision,
                a.explanation,
                COALESCE(a.severity, 'INFO') AS severity
            FROM anomalies a
            LEFT JOIN alert_acknowledgements aa
                ON aa.anomaly_id = a.id
               AND aa.username = '{safe_username.replace("'", "''")}'
            WHERE a.decision = 'ALERT'
              AND aa.id IS NULL
            ORDER BY a.event_time DESC, a.id DESC
            LIMIT {int(limit)}
            """
        )

    def get_decisions(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.run_query(
            f"""
            SELECT event_time, transaction_id, decision, confidence_score, risk_probability, final_score, severity
            FROM decisions
            ORDER BY id DESC
            LIMIT {int(limit)}
            """
        )

    def get_model_versions(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent model version records for governance display."""
        return self.run_query(
            f"""
            SELECT event_time, model_name, version, metadata
            FROM model_versions
            ORDER BY id DESC
            LIMIT {int(limit)}
            """
        )

    def log_agent_output(
        self,
        tenant_id: int,
        agent_name: str,
        transaction_id: str,
        score: float,
        confidence: float,
        payload: str,
    ) -> None:
        """Persist agent-level outputs for traceability."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_outputs (event_time, tenant_id, agent_name, transaction_id, score, confidence, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now_ist_iso(), tenant_id, agent_name, transaction_id, score, confidence, payload),
            )
            connection.commit()

    def get_agent_outputs(self, tenant_id: int = 1, limit: int = 100) -> list[dict[str, Any]]:
        return self.run_query(
            f"""
            SELECT event_time, tenant_id, agent_name, transaction_id, score, confidence, payload
            FROM agent_outputs
            WHERE tenant_id = {int(tenant_id)}
            ORDER BY id DESC
            LIMIT {int(limit)}
            """
        )

    def create_task(
        self,
        tenant_id: int,
        title: str,
        description: str,
        priority: str,
        owner: str,
        source_transaction_id: str,
        created_by: str,
        workflow_state: str,
    ) -> dict[str, Any]:
        """Create a task if an equivalent open task does not already exist."""
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT id, title, status, priority, owner, source_transaction_id, created_by, workflow_state
                FROM tasks
                WHERE tenant_id = ? AND source_transaction_id = ? AND workflow_state = ? AND status IN ('OPEN', 'PENDING')
                ORDER BY id DESC LIMIT 1
                """,
                (tenant_id, source_transaction_id, workflow_state),
            ).fetchone()
            if existing is not None:
                return dict(existing)
            cursor = connection.execute(
                """
                INSERT INTO tasks (event_time, tenant_id, title, description, status, priority, owner, source_transaction_id, created_by, workflow_state)
                VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?)
                """,
                (now_ist_iso(), tenant_id, title, description, priority, owner, source_transaction_id, created_by, workflow_state),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
        self.save_log(created_by, "task_created", f"{title} | {source_transaction_id}")
        return dict(row)

    def get_tasks(self, tenant_id: int = 1, limit: int = 100) -> list[dict[str, Any]]:
        return self.run_query(
            f"""
            SELECT event_time, title, description, status, priority, owner, source_transaction_id, created_by, workflow_state
            FROM tasks
            WHERE tenant_id = {int(tenant_id)}
            ORDER BY id DESC
            LIMIT {int(limit)}
            """
        )

    def create_approval(
        self,
        tenant_id: int,
        entity_type: str,
        entity_id: str,
        step_name: str,
        approver: str,
        status: str,
        comments: str,
    ) -> dict[str, Any]:
        """Create an approval step unless a pending one already exists."""
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT id, entity_type, entity_id, step_name, approver, status, comments
                FROM approvals
                WHERE tenant_id = ? AND entity_type = ? AND entity_id = ? AND step_name = ? AND status = 'PENDING'
                ORDER BY id DESC LIMIT 1
                """,
                (tenant_id, entity_type, entity_id, step_name),
            ).fetchone()
            if existing is not None:
                return dict(existing)
            cursor = connection.execute(
                """
                INSERT INTO approvals (event_time, tenant_id, entity_type, entity_id, step_name, approver, status, comments)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now_ist_iso(), tenant_id, entity_type, entity_id, step_name, approver, status, comments),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM approvals WHERE id = ?", (cursor.lastrowid,)).fetchone()
        self.save_log(approver, "approval_created", f"{entity_type}:{entity_id} | {step_name}")
        return dict(row)

    def get_approvals(self, tenant_id: int = 1, limit: int = 100) -> list[dict[str, Any]]:
        return self.run_query(
            f"""
            SELECT event_time, entity_type, entity_id, step_name, approver, status, comments
            FROM approvals
            WHERE tenant_id = {int(tenant_id)}
            ORDER BY id DESC
            LIMIT {int(limit)}
            """
        )

    def save_memory_feedback(self, tenant_id: int, interaction_key: str, feedback: str, notes: str = "") -> None:
        """Persist adaptive memory feedback from users or workflows."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_feedback (event_time, tenant_id, interaction_key, feedback, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (now_ist_iso(), tenant_id, interaction_key, feedback, notes),
            )
            connection.commit()

    def get_memory_feedback(self, tenant_id: int = 1, limit: int = 50) -> list[dict[str, Any]]:
        return self.run_query(
            f"""
            SELECT event_time, interaction_key, feedback, notes
            FROM memory_feedback
            WHERE tenant_id = {int(tenant_id)}
            ORDER BY id DESC
            LIMIT {int(limit)}
            """
        )
