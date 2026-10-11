from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkflowResult:
    tasks_created: list[dict]
    approvals_created: list[dict]
    escalation_level: str
    summary: str


class WorkflowEngine:
    """Event-driven workflow orchestration for tasks and approvals."""

    def __init__(self, database_manager) -> None:
        self.database = database_manager

    def orchestrate(
        self,
        tenant_id: int,
        transaction_id: str,
        decision: str,
        severity: str,
        recommendation: str,
        created_by: str,
        requires_approval: bool,
    ) -> WorkflowResult:
        tasks_created: list[dict] = []
        approvals_created: list[dict] = []
        escalation = "none"

        if decision in {"ALERT", "INVESTIGATE"}:
            task = self.database.create_task(
                tenant_id=tenant_id,
                title=f"{decision} review for {transaction_id}",
                description=recommendation,
                priority=severity,
                owner="finance-ops",
                source_transaction_id=transaction_id,
                created_by=created_by,
                workflow_state="open",
            )
            tasks_created.append(task)
            escalation = "workflow-open"

        if requires_approval:
            steps = ["Finance Manager", "CFO"] if severity == "CRITICAL" else ["Finance Manager"]
            for step in steps:
                approval = self.database.create_approval(
                    tenant_id=tenant_id,
                    entity_type="decision",
                    entity_id=transaction_id,
                    step_name=step,
                    approver=step.lower().replace(" ", "_"),
                    status="PENDING",
                    comments=recommendation,
                )
                approvals_created.append(approval)
            escalation = "approval-required"

        return WorkflowResult(
            tasks_created=tasks_created,
            approvals_created=approvals_created,
            escalation_level=escalation,
            summary=(
                f"Created {len(tasks_created)} task(s) and {len(approvals_created)} approval step(s) "
                f"for {transaction_id}."
            ),
        )
