from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
from typing import Any

import pandas as pd

from apscheduler.schedulers.background import BackgroundScheduler

from agents.anomaly_agent import AnomalyAgent
from agents.chat_agent import ChatAgent
from agents.consensus_agent import ConsensusAgent
from agents.explanation_agent import ExplanationAgent
from agents.forecast_agent import ForecastAgent
from agents.risk_agent import RiskAgent
from agents.simulation_agent import SimulationAgent
from analytics.bayesian_risk import compute_bayesian_risk
from analytics.counterfactual import compute_counterfactual_impact
from analytics.financial_os import (
    compute_budget_vs_actual,
    compute_cash_flow_intelligence,
    compute_cost_optimization,
    compute_financial_health_score,
    compute_loan_credit_intelligence,
    compute_risk_exposure,
)
from analytics.impact_propagation import build_financial_impact_graph
from chatbot.interface import ChatInterface
from models.autoencoder import AutoencoderModel
from models.isolation_forest import IsolationForestModel
from services.access_control import AccessControl
from services.decision_engine import DecisionIntelligenceEngine
from services.policy_engine import PolicyEngine
from services.workflow_engine import WorkflowEngine
from utils.database import DatabaseManager
from utils.email_alert import send_email_alert
from utils.logger import get_logger
from utils.preprocessing import (
    apply_invoice_payment_rules,
    append_erp_refresh,
    compute_zscore_anomalies,
    dampen_benign_profitable_records,
    engineer_financial_features,
    generate_basic_financial_insights,
    load_csv_data,
    preprocess_financial_data,
    transform_financial_data,
)


@dataclass
class SystemArtifacts:
    context: dict[str, Any]


class RationalAgentEngine:
    """Decision engine that maps risk evidence into an action."""

    def decide(self, row) -> str:
        anomaly_score = float(row["anomaly_score"])
        risk_level = row["risk_level"]
        historical_pattern = float(row["revenue_growth"])

        if anomaly_score >= 0.8 or (risk_level == "HIGH" and historical_pattern < 0):
            return "ALERT"
        if anomaly_score < 0.4 and risk_level == "LOW":
            return "IGNORE"
        return "INVESTIGATE"


class MonitoringService:
    """Application service that coordinates preprocessing, agents, and persistence."""

    def __init__(
        self,
        data_path: str = "data/financial_data.csv",
        training_data_path: str = "data/training_financial_data.csv",
        expanded_training_data_path: str = "data/expanded_training_financial_data.csv",
        database_manager: DatabaseManager | None = None,
    ) -> None:
        self.logger = get_logger()
        self.data_path = Path(data_path)
        self.training_data_path = Path(training_data_path)
        self.expanded_training_data_path = Path(expanded_training_data_path)
        self.database = database_manager or DatabaseManager()
        self.scheduler: BackgroundScheduler | None = None
        self.consensus_agent = ConsensusAgent()
        self.decision_engine = DecisionIntelligenceEngine()
        self.policy_engine = PolicyEngine()
        self.access_control = AccessControl()
        self.workflow_engine = WorkflowEngine(self.database)

    def refresh_source_data(self) -> None:
        df = load_csv_data(self.data_path)
        append_erp_refresh(df, periods=1).to_csv(self.data_path, index=False)
        self.logger.info("ERP refresh completed successfully.")

    def initialize_scheduler(self) -> BackgroundScheduler:
        if self.scheduler is None:
            self.scheduler = BackgroundScheduler()
            self.scheduler.add_job(self.refresh_source_data, "interval", minutes=30, id="erp_refresh", replace_existing=True)
            self.scheduler.start()
            self.logger.info("Background scheduler started.")
        return self.scheduler

    def load_shared_input(self, username: str | None = None):
        """Load the latest shared dataset when one is active."""
        tenant_id = int(self.database.get_user_profile(username).get("tenant_id", 1)) if username else 1
        state = self.database.get_shared_input_state(tenant_id=tenant_id)
        shared_path = Path("data/shared_input.csv")
        if not state or not state.get("is_active") or not shared_path.exists():
            return None, None
        df = load_csv_data(shared_path)
        return df, state

    def build_preferred_context(self, username: str | None = None) -> dict[str, Any]:
        """Build context from shared input when available, otherwise from the default dataset."""
        shared_df, shared_state = self.load_shared_input(username=username)
        if shared_df is not None and shared_state is not None:
            token = f"shared::{shared_state.get('updated_at', '')}"
            context = self.build_context_from_serialized(shared_df.to_json(date_format="iso", orient="records"), token, username or "")
        else:
            raw_df = load_csv_data(self.data_path)
            token = f"default::{self.data_path.stat().st_mtime_ns if self.data_path.exists() else 0}"
            context = self.build_context_from_serialized(raw_df.to_json(date_format="iso", orient="records"), token, username or "")
        context["shared_input_state"] = shared_state
        return context

    def save_shared_input(self, df, source_label: str, username: str) -> None:
        """Persist a dataset for cross-page sharing."""
        self.database.save_shared_input(df, source_label, username)

    def clear_shared_input(self, username: str) -> None:
        """Reset the cross-page shared dataset."""
        self.database.clear_shared_input(username)

    def save_email_alert_settings(self, settings: dict[str, str]) -> None:
        """Persist email alert configuration."""
        self.database.save_email_alert_settings(settings)

    def get_email_alert_settings(self) -> dict[str, str]:
        """Return persisted email alert configuration."""
        return self.database.get_email_alert_settings()

    @lru_cache(maxsize=8)
    def build_context_from_serialized(self, serialized_data: str, data_token: str, username: str = "") -> dict[str, Any]:
        """Build and cache context from a serialized dataset snapshot."""
        _ = (data_token, username)
        input_df = pd.read_json(serialized_data)
        return self.build_context(input_df=input_df, username=username)

    @lru_cache(maxsize=4)
    def _get_training_artifacts(self, training_token: str):
        """Build reusable training artifacts once per training-data snapshot."""
        _ = training_token
        training_raw = load_csv_data(self.training_data_path)
        expanded_training_raw = (
            load_csv_data(self.expanded_training_data_path)
            if self.expanded_training_data_path.exists()
            else training_raw.copy()
        )
        default_raw = load_csv_data(self.data_path)
        combined_training_raw = pd.concat([expanded_training_raw, training_raw, default_raw], ignore_index=True).drop_duplicates(
            subset=["date", "transaction_id"],
            keep="last",
        )
        training_preprocessed = preprocess_financial_data(combined_training_raw)

        isolation_model = IsolationForestModel()
        isolation_model.fit(training_preprocessed.feature_matrix)
        self.database.log_model_version("IsolationForest", "1.0.1", "contamination=0.12;n_estimators=200;cached=true")

        autoencoder_model = AutoencoderModel(input_dim=training_preprocessed.feature_matrix.shape[1], epochs=60)
        autoencoder_model.fit(training_preprocessed.feature_matrix)
        self.database.log_model_version("Autoencoder", "1.0.1", f"input_dim={training_preprocessed.feature_matrix.shape[1]};cached=true")
        synced_rows = self.database.sync_dataset_to_mysql(
            combined_training_raw,
            source_label="training_baseline",
            username="system",
            tenant_id=1,
            replace_existing=True,
        )
        if synced_rows:
            self.database.save_log(
                "system",
                "mysql_training_sync",
                f"Mirrored {synced_rows} baseline training rows into MySQL.",
            )
        return {
            "training_raw": training_raw,
            "expanded_training_raw": expanded_training_raw,
            "default_raw": default_raw,
            "combined_training_raw": combined_training_raw,
            "training_preprocessed": training_preprocessed,
            "isolation_model": isolation_model,
            "autoencoder_model": autoencoder_model,
        }

    def build_context(self, input_df=None, username: str = "") -> dict[str, Any]:
        user_profile = self.database.get_user_profile(username) if username else {"username": "system", "role": "admin", "tenant_id": 1, "tenant_name": "Default Finance"}
        tenant_id = int(user_profile.get("tenant_id", 1))
        permissions = self.access_control.permissions_for_role(user_profile.get("role", "viewer"))
        training_token = "|".join(
            str(path.stat().st_mtime_ns if path.exists() else 0)
            for path in [self.training_data_path, self.expanded_training_data_path, self.data_path]
        )
        artifacts = self._get_training_artifacts(training_token)
        training_raw = artifacts["training_raw"]
        expanded_training_raw = artifacts["expanded_training_raw"]
        default_raw = artifacts["default_raw"]
        combined_training_raw = artifacts["combined_training_raw"]
        training_preprocessed = artifacts["training_preprocessed"]
        isolation_model = artifacts["isolation_model"]
        autoencoder_model = artifacts["autoencoder_model"]

        raw_df = input_df.copy() if input_df is not None else default_raw.copy()
        if "date" in raw_df.columns:
            raw_df.loc[:, "date"] = pd.to_datetime(raw_df["date"], errors="coerce")
        inference_preprocessed = transform_financial_data(raw_df, training_preprocessed.scaler)

        anomaly_output = AnomalyAgent(isolation_model, autoencoder_model).run(
            inference_preprocessed.cleaned_df,
            inference_preprocessed.feature_matrix,
        )
        risk_output = RiskAgent().run(anomaly_output.dataframe, baseline_df=training_preprocessed.cleaned_df)
        zscore_df = compute_zscore_anomalies(risk_output.dataframe)
        zscore_df = apply_invoice_payment_rules(zscore_df)
        zscore_df = dampen_benign_profitable_records(zscore_df, baseline_df=training_preprocessed.cleaned_df)

        explanation_agent = ExplanationAgent(
            score_function=lambda values: -isolation_model.model.score_samples(values),
            background_data=training_preprocessed.feature_matrix,
            feature_names=training_preprocessed.feature_names,
        )
        forecast_source = raw_df.copy()
        chart_df = zscore_df.copy()
        comparison_source = pd.concat(
            [expanded_training_raw, training_raw, default_raw, raw_df],
            ignore_index=True,
        ).drop_duplicates(subset=["date", "transaction_id"], keep="last")
        comparison_source.loc[:, "date"] = pd.to_datetime(comparison_source["date"], errors="coerce")
        comparison_source = comparison_source.sort_values("date").reset_index(drop=True)
        if input_df is not None and len(raw_df) < 6:
            history_source = combined_training_raw.tail(12)
            forecast_source = pd.concat([history_source, raw_df], ignore_index=True).drop_duplicates(
                subset=["date", "transaction_id"],
                keep="last",
            )
            forecast_source.loc[:, "date"] = pd.to_datetime(forecast_source["date"], errors="coerce")
            forecast_source = forecast_source.sort_values("date").reset_index(drop=True)
            display_preprocessed = transform_financial_data(forecast_source, training_preprocessed.scaler)
            display_anomaly = AnomalyAgent(isolation_model, autoencoder_model).run(
                display_preprocessed.cleaned_df,
                display_preprocessed.feature_matrix,
            )
            chart_df = RiskAgent().run(display_anomaly.dataframe, baseline_df=training_preprocessed.cleaned_df).dataframe
            chart_df = compute_zscore_anomalies(chart_df)
            chart_df = apply_invoice_payment_rules(chart_df)
            chart_df = dampen_benign_profitable_records(chart_df, baseline_df=training_preprocessed.cleaned_df)
        comparison_preprocessed = transform_financial_data(comparison_source, training_preprocessed.scaler)
        comparison_anomaly = AnomalyAgent(isolation_model, autoencoder_model).run(
            comparison_preprocessed.cleaned_df,
            comparison_preprocessed.feature_matrix,
        )
        comparison_df = RiskAgent().run(comparison_anomaly.dataframe, baseline_df=training_preprocessed.cleaned_df).dataframe
        comparison_df = compute_zscore_anomalies(comparison_df)
        comparison_df = apply_invoice_payment_rules(comparison_df)
        comparison_df = dampen_benign_profitable_records(comparison_df, baseline_df=training_preprocessed.cleaned_df)
        forecast_output = ForecastAgent().run(engineer_financial_features(forecast_source))
        simulation_agent = SimulationAgent()
        cash_flow_intelligence = compute_cash_flow_intelligence(comparison_df)
        budget_variance = compute_budget_vs_actual(comparison_df)
        cost_optimization = compute_cost_optimization(comparison_df)

        rational_engine = RationalAgentEngine()
        final_df = zscore_df.copy()
        decisions: list[str] = []
        explanations: list[str] = []
        alerts: list[dict[str, Any]] = []
        decision_records: list[dict[str, Any]] = []
        impact_nodes: list[dict[str, Any]] = []
        impact_edges: list[tuple[str, str]] = []
        forecast_source_for_risk = engineer_financial_features(forecast_source)
        forecast_risk_value = 0.0
        if len(forecast_source_for_risk) >= 2:
            recent_revenue_growth = forecast_source_for_risk["revenue"].pct_change().fillna(0.0).tail(3)
            recent_expense_growth = forecast_source_for_risk["expenses"].pct_change().fillna(0.0).tail(3)
            forecast_risk_value = round(
                min(
                    max(
                        abs(float(recent_revenue_growth.min())) * 0.6 + max(float(recent_expense_growth.max()), 0.0) * 0.4,
                        0.0,
                    ),
                    1.0,
                ),
                4,
            )

        historical_anomaly_frequency = round(float((training_preprocessed.cleaned_df["profit_margin"] < 0.12).mean()), 4)

        for index, row in final_df.iterrows():
            explanation = "Routine observation."
            if int(row["anomaly_label"]) == 1:
                explanation = explanation_agent.quick_explanation(inference_preprocessed.feature_matrix[index:index + 1]).explanation_text

            stress_result = simulation_agent.run(
                latest_record=row,
                revenue_drop_pct=0.1 if float(row["revenue_growth"]) < 0 else 0.0,
                expense_increase_pct=0.05 if float(row["expense_ratio"]) > 0.7 else 0.0,
            ).result
            bayesian = compute_bayesian_risk(
                anomaly_score=float(row["anomaly_score"]),
                forecast_risk=forecast_risk_value,
                historical_anomaly_frequency=historical_anomaly_frequency,
            )
            counterfactual = compute_counterfactual_impact(row, training_preprocessed.cleaned_df)
            impact = build_financial_impact_graph(row)
            consensus = self.consensus_agent.run(
                {
                    "anomaly_score": float(row["anomaly_score"]),
                    "risk_probability": bayesian.risk_probability,
                    "forecast_risk": forecast_risk_value,
                    "stress_risk": stress_result.risk_score,
                    "historical_anomaly_frequency": historical_anomaly_frequency,
                }
            )
            decision_result = self.decision_engine.evaluate(
                anomaly_score=float(row["anomaly_score"]),
                risk_probability=bayesian.risk_probability,
                forecast_risk=forecast_risk_value,
                stress_risk=stress_result.risk_score,
                historical_anomaly_frequency=historical_anomaly_frequency,
                financial_impact=counterfactual.financial_impact,
                consensus_confidence=consensus.consensus_confidence,
            )
            health_snapshot = compute_financial_health_score(comparison_df, bayesian.risk_probability)
            exposure = compute_risk_exposure(comparison_df, bayesian.risk_probability, float(row["anomaly_score"]))
            policy_result = self.policy_engine.evaluate(
                ml_decision=decision_result.decision,
                risk_probability=bayesian.risk_probability,
                financial_health_score=health_snapshot.score,
                liquidity_risk=cash_flow_intelligence.liquidity_risk,
                total_exposure=exposure.total_exposure,
                budget_profit_variance=budget_variance.profit_variance,
            )
            fallback_decision = rational_engine.decide(row)
            decision = policy_result.adjusted_decision
            if decision == "IGNORE" and fallback_decision != "IGNORE":
                decision = fallback_decision
            decisions.append(decision)
            explanations.append(explanation)
            self.database.log_agent_decision("RationalAgentEngine", decision, f"{row['transaction_id']} | {row['anomaly_score']:.3f}")
            self.database.log_decision(
                transaction_id=row["transaction_id"],
                decision=decision,
                confidence_score=decision_result.confidence_score,
                risk_probability=bayesian.risk_probability,
                final_score=consensus.final_score,
                recommended_action=decision_result.recommended_action,
                reasoning_trace=decision_result.reasoning_trace,
                severity=decision_result.severity,
            )
            self.database.log_agent_output(
                tenant_id=tenant_id,
                agent_name="ConsensusAgent",
                transaction_id=row["transaction_id"],
                score=consensus.final_score,
                confidence=consensus.consensus_confidence,
                payload=str(consensus.weighted_components),
            )
            self.database.log_agent_output(
                tenant_id=tenant_id,
                agent_name="BayesianRiskAgent",
                transaction_id=row["transaction_id"],
                score=bayesian.risk_probability,
                confidence=1 - bayesian.uncertainty,
                payload=str(bayesian.components),
            )
            decision_record = {
                "transaction_id": row["transaction_id"],
                "decision": decision,
                "confidence_score": decision_result.confidence_score,
                "risk_probability": bayesian.risk_probability,
                "uncertainty": bayesian.uncertainty,
                "forecast_risk": forecast_risk_value,
                "stress_risk": stress_result.risk_score,
                "historical_anomaly_frequency": historical_anomaly_frequency,
                "financial_impact": counterfactual.financial_impact,
                "counterfactual_summary": counterfactual.summary,
                "reasoning_trace": decision_result.reasoning_trace,
                "recommended_action": decision_result.recommended_action,
                "severity": decision_result.severity,
                "consensus_confidence": consensus.consensus_confidence,
                "final_score": consensus.final_score,
                "impact_chain": impact.chain_text,
                "weighted_components": consensus.weighted_components,
                "policy_flags": policy_result.policy_flags,
                "policy_rationale": policy_result.rationale,
            }
            decision_records.append(decision_record)
            workflow_result = self.workflow_engine.orchestrate(
                tenant_id=tenant_id,
                transaction_id=row["transaction_id"],
                decision=decision,
                severity=decision_result.severity,
                recommendation=decision_result.recommended_action,
                created_by=username or "system",
                requires_approval=policy_result.requires_approval,
            )

            if decision == "ALERT":
                self.database.log_anomaly(
                    event_time=str(row["date"]),
                    transaction_id=row["transaction_id"],
                    anomaly_score=float(row["anomaly_score"]),
                    risk_level=row["risk_level"],
                    decision=decision,
                    explanation=explanation,
                    severity=decision_result.severity,
                )
                recipients = [
                    email.strip()
                    for email in (
                        self.get_email_alert_settings().get("recipients")
                        or os.getenv("ALERT_RECIPIENTS", "")
                    ).split(",")
                    if email.strip()
                ]
                if recipients:
                    signature = f"{decision}:{decision_result.severity}:{round(float(row['anomaly_score']), 2)}"
                    dedupe_key = f"alert_dedupe.{tenant_id}.{row['transaction_id']}"
                    last_signature = self.database.get_app_setting(dedupe_key, "")
                    if last_signature != signature:
                        send_email_alert(
                            subject=f"Financial alert for {row['transaction_id']}",
                            body=(
                                f"Anomaly score: {float(row['anomaly_score']):.2f}\n"
                                f"Risk probability: {bayesian.risk_probability:.2f}\n"
                                f"Financial impact: {counterfactual.financial_impact:,.0f}\n"
                                f"Policy rationale: {policy_result.rationale}\n"
                                f"Workflow summary: {workflow_result.summary}\n"
                                f"Reasoning:\n{decision_result.reasoning_trace}\n\n"
                                f"Recommendation: {decision_result.recommended_action}"
                            ),
                            recipients=recipients,
                            severity=decision_result.severity,
                            config=self.get_email_alert_settings(),
                        )
                        self.database.set_app_setting(dedupe_key, signature)
                alerts.append(
                    {
                        "transaction_id": row["transaction_id"],
                        "anomaly_score": float(row["anomaly_score"]),
                        "risk_level": row["risk_level"],
                        "decision": decision,
                        "explanation": explanation,
                        "severity": decision_result.severity,
                        "risk_probability": bayesian.risk_probability,
                        "financial_impact": counterfactual.financial_impact,
                        "reasoning_trace": decision_result.reasoning_trace,
                        "recommended_action": decision_result.recommended_action,
                        "workflow_summary": workflow_result.summary,
                    }
                )
            if index == len(final_df) - 1:
                impact_nodes = impact.nodes
                impact_edges = impact.edges

        email_alert_settings = self.get_email_alert_settings()
        email_alert_enabled = (
            email_alert_settings.get("enabled", "").lower() == "true"
            and bool(email_alert_settings.get("smtp_host"))
            and bool(email_alert_settings.get("recipients"))
        ) or bool(os.getenv("ALERT_SMTP_HOST") and os.getenv("ALERT_RECIPIENTS"))

        final_df["decision"] = decisions
        final_df["explanation"] = explanations
        final_df["uploaded"] = input_df is not None
        if decision_records:
            decision_df = pd.DataFrame(decision_records)
            extra_columns = [column for column in decision_df.columns if column == "transaction_id" or column not in final_df.columns]
            final_df = final_df.merge(decision_df[extra_columns], on="transaction_id", how="left")
        latest_decision = decision_records[-1] if decision_records else {}
        alert_history = self.database.get_decisions(limit=25)
        model_versions = self.database.get_model_versions(limit=10)
        health_score = compute_financial_health_score(comparison_df, latest_decision.get("risk_probability", 0.0) if latest_decision else 0.0)
        risk_exposure = compute_risk_exposure(comparison_df, latest_decision.get("risk_probability", 0.0) if latest_decision else 0.0, float(final_df.iloc[-1]["anomaly_score"]))
        loan_credit = compute_loan_credit_intelligence(comparison_df, latest_decision.get("risk_probability", 0.0) if latest_decision else 0.0)
        tasks = self.database.get_tasks(tenant_id=tenant_id, limit=20) if permissions.get("view_governance", False) else []
        approvals = self.database.get_approvals(tenant_id=tenant_id, limit=20) if permissions.get("view_governance", False) else []
        agent_outputs = self.database.get_agent_outputs(tenant_id=tenant_id, limit=20) if permissions.get("view_governance", False) else []
        memory_feedback = self.database.get_memory_feedback(tenant_id=tenant_id, limit=20) if permissions.get("view_governance", False) else []
        security_users = self.database.list_users() if permissions.get("manage_users", False) else []
        login_attempts = self.database.get_login_attempts(limit=50) if permissions.get("manage_security", False) else []
        pending_user_approvals = self.database.get_pending_user_approvals(tenant_id=tenant_id) if permissions.get("manage_users", False) else []

        chat_interface = ChatInterface(ChatAgent(self.database), self.database)
        self.logger.info("System context built successfully.")
        return {
            "dataframe": final_df,
            "chart_dataframe": chart_df,
            "comparison_dataframe": comparison_df,
            "feature_matrix": inference_preprocessed.feature_matrix,
            "feature_names": inference_preprocessed.feature_names,
            "revenue_forecast": forecast_output.revenue_forecast,
            "expense_forecast": forecast_output.expense_forecast,
            "simulation_agent": simulation_agent,
            "explanation_agent": explanation_agent,
            "chat_interface": chat_interface,
            "alerts": alerts,
            "database_manager": self.database,
            "insights": generate_basic_financial_insights(raw_df),
            "latest_decision": latest_decision,
            "decision_history": alert_history,
            "impact_nodes": impact_nodes,
            "impact_edges": impact_edges,
            "model_versions": model_versions,
            "email_alert_enabled": email_alert_enabled,
            "email_alert_settings": email_alert_settings,
            "training_sample_count": int(len(combined_training_raw)),
            "training_data_file": str(self.expanded_training_data_path if self.expanded_training_data_path.exists() else self.training_data_path),
            "cash_flow_intelligence": cash_flow_intelligence,
            "budget_variance": budget_variance,
            "cost_optimization": cost_optimization,
            "health_score": health_score,
            "risk_exposure": risk_exposure,
            "loan_credit": loan_credit,
            "tasks": tasks,
            "approvals": approvals,
            "agent_outputs": agent_outputs,
            "memory_feedback": memory_feedback,
            "security_users": security_users,
            "login_attempts": login_attempts,
            "pending_user_approvals": pending_user_approvals,
            "user_profile": user_profile,
            "permissions": permissions,
        }
