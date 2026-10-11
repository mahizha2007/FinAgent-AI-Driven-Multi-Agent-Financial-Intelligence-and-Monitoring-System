from __future__ import annotations

from functools import lru_cache
from typing import Any

from services.monitoring_service import MonitoringService
from utils.database import DatabaseManager
from utils.logger import get_logger


LOGGER = get_logger()
DATABASE = DatabaseManager()
SERVICE = MonitoringService(database_manager=DATABASE)


def initialize_scheduler():
    """Initialize the background ERP refresh scheduler."""
    return SERVICE.initialize_scheduler()


@lru_cache(maxsize=1)
def build_system_context() -> dict[str, Any]:
    """Build and cache the default system context from the baseline dataset."""
    return SERVICE.build_context()


if __name__ == "__main__":
    initialize_scheduler()
    context = build_system_context()
    print("System initialized successfully.")
    print(context["dataframe"].tail(5)[["date", "transaction_id", "anomaly_score", "risk_level", "decision"]])
