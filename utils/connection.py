from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
except Exception:  # pragma: no cover - optional dependency
    mysql = None
    MySQLError = Exception


@dataclass
class MySQLConfig:
    host: str = os.getenv("MYSQL_HOST", "localhost")
    port: int = int(os.getenv("MYSQL_PORT", "3306"))
    user: str = os.getenv("MYSQL_USER", "root")
    password: str = os.getenv("MYSQL_PASSWORD", "1919")
    database: str = os.getenv("MYSQL_DATABASE", "financial_monitor")


def get_mysql_connection(config: MySQLConfig | None = None):
    """Return a MySQL connection when the driver and server are available."""
    if mysql is None:
        return None

    current = config or MySQLConfig()
    try:
        bootstrap = mysql.connector.connect(
            host=current.host,
            port=current.port,
            user=current.user,
            password=current.password,
        )
        bootstrap_cursor = bootstrap.cursor()
        bootstrap_cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{current.database}`")
        bootstrap.commit()
        bootstrap_cursor.close()
        bootstrap.close()
        return mysql.connector.connect(
            host=current.host,
            port=current.port,
            user=current.user,
            password=current.password,
            database=current.database,
        )
    except MySQLError:
        return None


def initialize_mysql_schema(connection) -> bool:
    """Create MySQL tables used by the application."""
    if connection is None:
        return False

    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_name VARCHAR(255) NOT NULL,
            action VARCHAR(255) NOT NULL,
            message TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_query TEXT NOT NULL,
            response TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ingested_financial_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source_label VARCHAR(255),
            username VARCHAR(255) NOT NULL,
            tenant_id INT DEFAULT 1,
            record_date DATE,
            transaction_id VARCHAR(255),
            revenue DOUBLE,
            expenses DOUBLE,
            cash_flow DOUBLE,
            customer_count DOUBLE,
            accounts_receivable DOUBLE,
            inventory DOUBLE,
            marketing_spend DOUBLE,
            payment_status VARCHAR(64),
            outstanding_amount DOUBLE
        )
        """,
    ]

    cursor = connection.cursor()
    for statement in statements:
        cursor.execute(statement)
    connection.commit()
    cursor.close()
    return True
