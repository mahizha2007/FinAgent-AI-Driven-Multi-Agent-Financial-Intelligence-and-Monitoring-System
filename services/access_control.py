from __future__ import annotations


BASE_VIEWER_PERMISSIONS = {
    "view_dashboard",
    "view_overview",
    "view_compare",
    "view_decision_intelligence",
    "use_chat",
    "acknowledge_alerts",
}

ROLE_PERMISSIONS = {
    "admin": {
        *BASE_VIEWER_PERMISSIONS,
        "view_logs",
        "view_operating_system",
        "view_governance",
        "view_explainability",
        "run_scenarios",
        "download_reports",
        "manage_alerts",
        "manage_workflows",
        "manage_users",
        "manage_security",
        "refresh_context",
        "submit_data",
        "approve_items",
    },
    "reviewer": {
        *BASE_VIEWER_PERMISSIONS,
        "view_logs",
        "view_operating_system",
        "view_governance",
        "download_reports",
        "approve_items",
    },
    "analyst": {
        *BASE_VIEWER_PERMISSIONS,
        "view_operating_system",
        "view_explainability",
        "run_scenarios",
        "download_reports",
        "refresh_context",
        "submit_data",
    },
    "viewer": BASE_VIEWER_PERMISSIONS,
}


ROLE_LABELS = {
    "admin": "Administrator",
    "reviewer": "Reviewer",
    "analyst": "Analyst",
    "viewer": "Viewer",
}


class AccessControl:
    """Role-based access control helper for UI and backend permissions."""

    def normalize_role(self, role: str | None) -> str:
        """Return a known role name with viewer as the safe default."""
        normalized = (role or "viewer").strip().lower()
        return normalized if normalized in ROLE_PERMISSIONS else "viewer"

    def can(self, role: str, permission: str) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.normalize_role(role), set())

    def permissions_for_role(self, role: str | None) -> dict[str, bool]:
        """Return a boolean permission map for a role."""
        normalized = self.normalize_role(role)
        allowed = ROLE_PERMISSIONS.get(normalized, set())
        return {permission: permission in allowed for permission in sorted({item for values in ROLE_PERMISSIONS.values() for item in values})}

    def list_roles(self) -> list[str]:
        """Return supported role names in display order."""
        return ["admin", "reviewer", "analyst", "viewer"]

    def label_for_role(self, role: str | None) -> str:
        """Return a user-friendly label for a role."""
        normalized = self.normalize_role(role)
        return ROLE_LABELS.get(normalized, "Viewer")
