from __future__ import annotations

from calendar import month_name
from dataclasses import dataclass
from typing import Any
import re

import pandas as pd

from analytics.xirr import xirr
from analytics.stress_testing import parse_scenario_text, run_stress_test
from chatbot.nlp import parse_financial_query


@dataclass
class ChatResponse:
    answer: str
    action_type: str
    action_payload: dict[str, Any]


class ChatAgent:
    """Rule-based financial assistant with structured reasoning and memory awareness."""

    def __init__(self, database_manager, memory_limit: int = 5) -> None:
        self.database_manager = database_manager
        self.memory_limit = memory_limit

    def _personalize(self) -> str:
        return ""

    @staticmethod
    def _safe_value(value: Any, default: str = "N/A") -> str:
        """Return a simple printable value for chat responses."""
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default

    @staticmethod
    def _format_reasoning(insight: str, reason: str, recommendation: str, context_line: str = "") -> str:
        parts = []
        if context_line:
            parts.append(context_line.strip())
        if insight:
            parts.append(insight.strip().rstrip(".") + ".")
        if reason:
            parts.append(reason.strip().rstrip(".") + ".")
        if recommendation:
            parts.append(recommendation.strip().rstrip(".") + ".")
        return " ".join(part for part in parts if part).strip()

    @staticmethod
    def _stylize_response(text: str, chat_style: str) -> str:
        """Render a concise direct answer."""
        return text

    def _capabilities_summary(self, permissions: dict[str, bool]) -> str:
        """Summarize what the assistant can currently help with."""
        areas = [
            "dashboard summaries",
            "anomaly review",
            "risk interpretation",
            "revenue and profit comparisons",
            "forecast discussion",
            "scenario questions",
            "invoice payment status reasoning",
            "training-data and model context",
        ]
        if permissions.get("view_logs", False):
            areas.append("log and audit guidance")
        if permissions.get("download_reports", False):
            areas.append("report-download guidance")
        return ", ".join(areas[:-1]) + f", and {areas[-1]}" if len(areas) > 1 else areas[0]

    def _answer_general_finance_question(self, query: str, context: dict[str, Any], latest, latest_decision: dict[str, Any], memory_context: str) -> ChatResponse:
        """Provide a broad finance-aware answer for loosely phrased questions."""
        lower = query.lower()
        comparison_df: pd.DataFrame = context.get("comparison_dataframe", context["dataframe"])
        permissions = context.get("permissions", {})

        def pack(answer: str, action_type: str = "function", action_payload: dict[str, Any] | None = None) -> ChatResponse:
            return ChatResponse(
                answer=self._stylize_response(answer, context.get("chat_style", "Operator")),
                action_type=action_type,
                action_payload=action_payload or {},
            )

        if "revenue" in lower:
            total_revenue = float(comparison_df["revenue"].sum())
            return pack(
                self._format_reasoning(
                    insight=f"Latest revenue is {float(latest['revenue']):,.0f}, and the current comparison window totals {total_revenue:,.0f}.",
                    reason="I used the live dashboard dataset plus the comparison context to answer a general revenue question.",
                    recommendation="If you want a deeper answer, ask me to compare two periods or explain why revenue changed.",
                    context_line=memory_context,
                ),
                action_payload={"name": "general_revenue_answer"},
            )
        if "profit" in lower or "margin" in lower:
            return pack(
                self._format_reasoning(
                    insight=f"Latest profit is {float(latest['profit']):,.0f} with margin {float(latest['profit_margin']):.2%}.",
                    reason="That combines the latest revenue and expense values already processed by the monitoring pipeline.",
                    recommendation="Ask for a period comparison if you want to see whether profit is improving or deteriorating over time.",
                    context_line=memory_context,
                ),
                action_payload={"name": "general_profit_answer"},
            )
        if "expense" in lower or "cost" in lower:
            return pack(
                self._format_reasoning(
                    insight=f"Latest expenses are {float(latest['expenses']):,.0f} with an expense ratio of {float(latest['expense_ratio']):.2%}.",
                    reason="The system tracks expense pressure both directly and as a ratio against revenue.",
                    recommendation="If you want, ask me whether expenses are growing faster than revenue.",
                    context_line=memory_context,
                ),
                action_payload={"name": "general_expense_answer"},
            )
        if "invoice" in lower or "outstanding" in lower or "paid" in lower:
            payment_status = self._safe_value(latest.get("payment_status"), "PAID")
            outstanding_amount = float(latest.get("outstanding_amount", latest.get("accounts_receivable", 0.0)))
            return pack(
                self._format_reasoning(
                    insight=f"Latest invoice status is {payment_status} with outstanding amount {outstanding_amount:,.0f}.",
                    reason="Invoice-style records are now parsed for payment status, paid amount, and receivables so I can answer loosely phrased invoice questions.",
                    recommendation="Ask me to list unpaid or partially paid invoices if you want a focused receivables view.",
                    context_line=memory_context,
                ),
                action_payload={"name": "general_invoice_answer"},
            )
        if "log" in lower or "audit" in lower:
            if permissions.get("view_logs", False):
                return pack(
                    self._format_reasoning(
                        insight="Audit logs are available to your current role.",
                        reason="Your role includes log visibility, so you can review events, downloads, uploads, and errors in the Logs page.",
                        recommendation="Open Logs if you want the full event history or ask me what kind of events are being tracked.",
                        context_line=memory_context,
                    ),
                    action_payload={"name": "general_log_answer"},
                )
            return pack(
                self._format_reasoning(
                    insight="Log access is restricted for your current role.",
                    reason="The system enforces role-based visibility for audit data.",
                    recommendation="Ask an admin if you need audit access.",
                    context_line=memory_context,
                ),
                "restricted",
                {"required_permission": "view_logs"},
            )
        return pack(
            self._format_reasoning(
                insight=f"The latest decision is {latest_decision.get('decision', latest.get('decision', 'UNKNOWN'))} and the current anomaly score is {float(latest.get('anomaly_score', 0.0)):.2f}.",
                reason="I answered from the live context because your question was broad rather than tied to a single narrow intent.",
                recommendation="Ask a follow-up like 'why?', 'compare this month with last month', or 'show unpaid invoices' for a sharper answer.",
                context_line=memory_context,
            ),
            action_payload={"name": "general_finance_answer"},
        )

    def respond(self, query: str, context: dict[str, Any]) -> ChatResponse:
        """Map a user query to structured financial reasoning and actions."""
        lower = query.lower()
        memory_context = self._personalize()
        dataframe: pd.DataFrame = context["dataframe"]
        latest = dataframe.iloc[-1]
        highest = dataframe.sort_values("anomaly_score", ascending=False).iloc[0]
        latest_decision = context.get("latest_decision", {})
        parsed = parse_financial_query(query)
        chat_style = context.get("chat_style", "Operator")
        permissions = context.get("permissions", {})

        def pack(answer: str, action_type: str, action_payload: dict[str, Any]) -> ChatResponse:
            return ChatResponse(
                answer=self._stylize_response(answer, chat_style),
                action_type=action_type,
                action_payload=action_payload,
            )

        if parsed.intent == "greeting":
            return pack(
                self._format_reasoning(
                    insight="Financial Copilot is online and synced to the live dashboard context.",
                    reason=(
                        f"I currently see the latest decision as {latest_decision.get('decision', latest.get('decision', 'UNKNOWN'))}, "
                        f"risk level {latest.get('risk_level', 'N/A')}, and anomaly score {latest.get('anomaly_score', 0.0):.2f}."
                    ),
                    recommendation="Ask about decisions, risk probability, logs, forecasts, scenarios, or the training dataset.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "greeting"},
            )

        if parsed.intent == "thanks":
            return pack(
                self._format_reasoning(
                    insight="You’re welcome.",
                    reason="I’m here to turn the live financial context into fast, useful answers.",
                    recommendation="Ask another question whenever you want a deeper read on anomalies, invoices, risk, forecasts, or decisions.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "thanks"},
            )

        if parsed.intent in {"help", "capabilities"}:
            return pack(
                self._format_reasoning(
                    insight="I can handle a much wider range of finance and dashboard questions now.",
                    reason=f"Right now I can help with {self._capabilities_summary(permissions)}.",
                    recommendation="Try natural prompts like 'summarize the dashboard', 'which invoices are unpaid?', 'compare profit this month vs last month', or 'what should we do next?'.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "capabilities"},
            )

        if parsed.intent == "current_summary":
            anomaly_count = int((dataframe["anomaly_label"] == 1).sum()) if "anomaly_label" in dataframe.columns else 0
            return pack(
                self._format_reasoning(
                    insight=(
                        f"Current snapshot: decision {latest_decision.get('decision', latest.get('decision', 'UNKNOWN'))}, "
                        f"risk {latest.get('risk_level', 'N/A')}, anomaly score {float(latest.get('anomaly_score', 0.0)):.2f}, "
                        f"and {anomaly_count} flagged anomaly record(s)."
                    ),
                    reason=(
                        f"Latest revenue is {float(latest.get('revenue', 0.0)):,.0f}, expenses are {float(latest.get('expenses', 0.0)):,.0f}, "
                        f"and profit is {float(latest.get('profit', 0.0)):,.0f}."
                    ),
                    recommendation="Ask me to drill into anomalies, invoices, decisions, comparisons, forecasts, or access permissions next.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "current_summary"},
            )

        if parsed.intent == "identity":
            return pack(
                self._format_reasoning(
                    insight="I am your financial decision copilot for this dashboard.",
                    reason=(
                        "I specialize in anomalies, risk, decisions, forecasts, scenarios, audit logs, and training-data awareness "
                        "using the live context from this system."
                    ),
                    recommendation="Ask me to compare periods, explain a decision, review logs, or summarize the current financial signal.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "identity"},
            )

        if parsed.intent == "off_topic":
            return pack(
                self._format_reasoning(
                    insight="I can still respond, but I’m strongest on finance and system questions.",
                    reason="This copilot is designed around the live financial dashboard rather than open-ended internet knowledge or entertainment topics.",
                    recommendation="Ask me something connected to finance, invoices, risk, comparisons, logs, forecasts, or decisions for the best answer.",
                    context_line=memory_context,
                ),
                "fallback",
                {"scope": "financial_only"},
            )

        if parsed.intent == "top_anomaly" or "highest anomaly" in lower or "top anomaly" in lower:
            insight = f"The strongest anomaly is {highest['transaction_id']} with score {highest['anomaly_score']:.2f}."
            reason = (
                f"It stands out because its risk level is {highest['risk_level']} and the system explanation says: "
                f"{highest['explanation']}"
            )
            recommendation = "Review the transaction, validate source records, and confirm whether an operational event caused the spike."
            return pack(
                self._format_reasoning(insight, reason, recommendation, memory_context),
                "function",
                {"name": "top_anomalies", "transaction_id": highest["transaction_id"]},
            )

        if parsed.intent == "count_anomalies":
            anomaly_count = int((dataframe["anomaly_label"] == 1).sum()) if "anomaly_label" in dataframe.columns else 0
            return pack(
                self._format_reasoning(
                    insight=f"There are currently {anomaly_count} flagged anomalies in the active dataset.",
                    reason="I counted records whose anomaly label is active in the live context.",
                    recommendation="Ask me to show anomalies or explain the top anomaly if you want the next level of detail.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "count_anomalies"},
            )

        if parsed.intent == "risk_probability":
            insight = (
                f"The latest Bayesian risk probability is {latest_decision.get('risk_probability', latest.get('risk_probability', 0.0)):.2f} "
                f"with uncertainty {latest_decision.get('uncertainty', latest.get('uncertainty', 0.0)):.2f}."
            )
            reason = (
                f"This uses anomaly score {latest['anomaly_score']:.2f}, forecast risk "
                f"{latest_decision.get('forecast_risk', 0.0):.2f}, and historical anomaly frequency "
                f"{latest_decision.get('historical_anomaly_frequency', 0.0):.2f}."
            )
            recommendation = "Use the probability with the decision confidence before escalating capital or operational actions."
            return pack(self._format_reasoning(insight, reason, recommendation, memory_context), "function", {"name": "risk_probability"})

        if parsed.intent == "period_compare":
            month_lookup = {name.lower(): idx for idx, name in enumerate(month_name) if name}
            found_months = [month_lookup[name] for name in month_lookup if name in lower]
            metric = "revenue"
            if "profit" in lower:
                metric = "profit"
            elif "expense" in lower:
                metric = "expenses"
            chart_df = context.get("chart_dataframe", dataframe).copy()
            chart_df["date"] = pd.to_datetime(chart_df["date"], errors="coerce")
            chart_df = chart_df.dropna(subset=["date"])
            if len(found_months) >= 2:
                month_a, month_b = found_months[0], found_months[1]
                bucket_a = chart_df[chart_df["date"].dt.month == month_a]
                bucket_b = chart_df[chart_df["date"].dt.month == month_b]
                if not bucket_a.empty and not bucket_b.empty:
                    total_a = float(bucket_a[metric].sum())
                    total_b = float(bucket_b[metric].sum())
                    delta = total_b - total_a
                    return pack(
                        self._format_reasoning(
                            insight=f"{month_name[month_b]} {metric} was {total_b:,.0f} versus {total_a:,.0f} in {month_name[month_a]}.",
                            reason=(
                                f"The interval delta is {delta:,.0f}, based on {len(bucket_a)} records for {month_name[month_a]} "
                                f"and {len(bucket_b)} records for {month_name[month_b]} from the active comparison dataset."
                            ),
                            recommendation="Open the Revenue Compare tab to inspect the same comparison visually and across other metrics.",
                            context_line=memory_context,
                        ),
                        "function",
                        {"name": "period_compare", "metric": metric},
                    )

        if parsed.intent == "latest_decision":
            insight = (
                f"The latest decision is {latest_decision.get('decision', latest.get('decision', 'UNKNOWN'))} "
                f"with confidence {latest_decision.get('confidence_score', 0.0):.2f}."
            )
            reason = latest_decision.get("reasoning_trace", f"Latest anomaly score is {latest['anomaly_score']:.2f}.")
            recommendation = latest_decision.get(
                "recommended_action",
                "Review the dashboard panels for more detail before taking action.",
            )
            return pack(self._format_reasoning(insight, reason, recommendation, memory_context), "function", {"name": "latest_decision"})

        if ("risk" in lower and "current" in lower) or "latest risk" in lower:
            insight = f"The latest risk level is {latest['risk_level']} with a score of {latest['risk_score']:.2f}."
            reason = (
                f"The latest anomaly score is {latest['anomaly_score']:.2f}, revenue growth is {latest['revenue_growth']:.2%}, "
                f"and the system decision is {latest['decision']}."
            )
            recommendation = (
                "Escalate to finance leadership if the risk remains high for multiple periods; otherwise monitor the next refresh."
                if latest["risk_level"] == "HIGH"
                else "Continue monitoring and compare the next reporting period before escalating."
            )
            return pack(self._format_reasoning(insight, reason, recommendation, memory_context), "function", {"name": "latest_risk"})

        if parsed.intent == "show_anomalies" or "show anomalies" in lower or "flagged transactions" in lower or "anomaly" in lower and "show" in lower:
            flagged = dataframe[dataframe["anomaly_label"] == 1].sort_values("anomaly_score", ascending=False).head(5)
            summary = "; ".join(
                f"{row.transaction_id} ({row.anomaly_score:.2f}, {row.risk_level})"
                for row in flagged.itertuples()
            ) if not flagged.empty else "No active anomalies were flagged in this run."
            sql = (
                "SELECT event_time, transaction_id, anomaly_score, risk_level "
                "FROM anomalies ORDER BY anomaly_score DESC LIMIT 5"
            )
            return pack(
                self._format_reasoning(
                    insight="The system has identified the most relevant flagged transactions.",
                    reason=summary,
                    recommendation="Investigate the top two anomalies first because they have the strongest combined anomaly and risk signal.",
                    context_line=memory_context,
                ),
                "sql",
                {"query": sql},
            )

        if parsed.intent == "invoice_status":
            invoice_df = dataframe.copy()
            if "payment_status" in invoice_df.columns:
                tracked = invoice_df[invoice_df["payment_status"].notna()].copy()
                if not tracked.empty:
                    unpaid = tracked[tracked["payment_status"].astype(str).str.upper() == "UNPAID"]
                    partial = tracked[tracked["payment_status"].astype(str).str.upper() == "PARTIALLY_PAID"]
                    total_outstanding = float(tracked.get("outstanding_amount", tracked.get("accounts_receivable", pd.Series(dtype=float))).fillna(0.0).sum())
                    return pack(
                        self._format_reasoning(
                            insight=f"I found {len(unpaid)} unpaid and {len(partial)} partially paid invoice records with total outstanding {total_outstanding:,.0f}.",
                            reason="Invoice-style records now carry payment status and outstanding amounts, so invoice-payment questions can be answered directly from the parsed data.",
                            recommendation="Treat unpaid and partially paid invoices as receivables risk and investigate the oldest or largest balances first.",
                            context_line=memory_context,
                        ),
                        "function",
                        {"name": "invoice_status"},
                    )

        if parsed.intent == "forecast_revenue" or "forecast" in lower and "revenue" in lower:
            forecast_df = context["revenue_forecast"].tail(3)
            summary = ", ".join(f"{row.ds.date()}: {row.yhat:,.0f}" for row in forecast_df.itertuples())
            return pack(
                self._format_reasoning(
                    insight="Revenue is forecasted to continue along the projected trend.",
                    reason=f"The next revenue forecast points are {summary}.",
                    recommendation="Compare forecasted revenue with operating plans and adjust spending if actuals start drifting below forecast.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "revenue_forecast"},
            )

        if parsed.intent == "forecast_expense" or "forecast" in lower and "expense" in lower:
            forecast_df = context["expense_forecast"].tail(3)
            summary = ", ".join(f"{row.ds.date()}: {row.yhat:,.0f}" for row in forecast_df.itertuples())
            return pack(
                self._format_reasoning(
                    insight="Expense pressure is reflected in the projected expense trend.",
                    reason=f"The next expense forecast points are {summary}.",
                    recommendation="Watch for expense growth outpacing revenue growth and tighten discretionary spend if that gap widens.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "expense_forecast"},
            )

        if parsed.intent == "xirr" or "xirr" in lower or "irr" in lower:
            cash_flows = [-100000, 18000, 24000, 28000, 62000]
            dates = ["2024-01-01", "2024-06-01", "2025-01-15", "2025-10-01", "2026-03-01"]
            result = xirr(cash_flows, dates) * 100
            return pack(
                self._format_reasoning(
                    insight=f"The illustrative XIRR is {result:.2f}%.",
                    reason="The calculation uses irregular cash-flow dates and a numerical XIRR solver implemented inside the project.",
                    recommendation="Use this as a return benchmark when comparing investment timing efficiency across scenarios.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "xirr"},
            )

        if parsed.intent == "scenario" or "what if" in lower or "revenue drops" in lower or ("expense" in lower and "%" in lower):
            revenue_drop_pct, expense_increase_pct = parse_scenario_text(query)
            simulation = run_stress_test(
                latest_record=latest,
                revenue_drop_pct=revenue_drop_pct,
                expense_increase_pct=expense_increase_pct,
            )
            return pack(
                self._format_reasoning(
                    insight=f"Under that scenario, stressed profit becomes {simulation.stressed_profit:,.0f}.",
                    reason=(
                        f"The model applied a revenue drop of {simulation.applied_revenue_drop:.0%} and an expense increase of "
                        f"{simulation.applied_expense_increase:.0%}, producing a profit impact of {simulation.profit_impact:,.0f}."
                    ),
                    recommendation="If the downside is unacceptable, reduce discretionary expenses and create a contingency revenue plan.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "scenario_simulation", "query": query, "risk_score": simulation.risk_score},
            )

        if parsed.intent == "reasoning" or "why" in lower and ("alert" in lower or "risk" in lower):
            insight = f"The latest system decision is {latest['decision']}."
            reason = latest_decision.get(
                "reasoning_trace",
                f"Anomaly score is {latest['anomaly_score']:.2f}, risk level is {latest['risk_level']}, and explanation is {latest['explanation']}",
            )
            recommendation = latest_decision.get(
                "recommended_action",
                "Treat ALERT as an escalation trigger, INVESTIGATE as a review cue, and IGNORE as low-priority monitoring.",
            )
            return pack(self._format_reasoning(insight, reason, recommendation, memory_context), "function", {"name": "decision_explanation"})

        if parsed.intent == "impact":
            insight = latest_decision.get("counterfactual_summary", "The latest financial impact estimate is available.")
            reason = latest_decision.get("impact_chain", "Impact propagation links revenue and expenses through profit, cash flow, and risk.")
            recommendation = latest_decision.get("recommended_action", "Use the impact analysis to prioritize operational review.")
            return pack(self._format_reasoning(insight, reason, recommendation, memory_context), "function", {"name": "impact_analysis"})

        if parsed.intent == "alert_history":
            history = context.get("decision_history", [])[:5]
            summary = "; ".join(
                f"{row['transaction_id']} ({row['decision']}, {row['severity']}, {row['confidence_score']:.2f})"
                for row in history
            ) if history else "No recent decision history is available."
            return pack(
                self._format_reasoning(
                    insight="Recent decision history is available for review.",
                    reason=summary,
                    recommendation="Look for repeated ALERT or INVESTIGATE outcomes to detect persistent control issues.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "alert_history"},
            )

        if parsed.intent == "recommendations":
            return pack(
                self._format_reasoning(
                    insight=f"The current recommendation is: {latest_decision.get('recommended_action', 'No recommendation available.')}",
                    reason=latest_decision.get("reasoning_trace", "The recommendation is generated from decision, risk, forecast, and impact signals."),
                    recommendation="Use the Decision Intelligence tab if you want the full governance and impact trace.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "recommendations"},
            )

        if parsed.intent == "master_draft":
            return pack(
                self._format_reasoning(
                    insight="A downloadable master draft is available in the dashboard.",
                    reason="The report compiles executive summary, reasoning trace, active alerts, impact chain, and governance metadata.",
                    recommendation="Open the Command Brief tab and download the PDF or CSV version.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "master_draft"},
            )

        if parsed.intent == "logs":
            if not permissions.get("view_logs", False):
                return pack(
                    self._format_reasoning(
                        insight="Log access is restricted for your current role.",
                        reason="Audit trails and detailed operational logs are available only to reviewer or admin users.",
                        recommendation="Ask an administrator for log access if you need audit-level traceability.",
                        context_line=memory_context,
                    ),
                    "restricted",
                    {"required_permission": "view_logs"},
                )
            return pack(
                self._format_reasoning(
                    insight="The full audit trail is available in the Logs panel.",
                    reason="You can filter by date and action type, view the full log history, and export the filtered logs as PDF or CSV.",
                    recommendation="Open the Logs panel for detailed traceability after uploads, alerts, downloads, and chatbot actions.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "logs"},
            )

        if parsed.intent == "training_data":
            return pack(
                self._format_reasoning(
                    insight=f"The anomaly models are currently trained on about {context.get('training_sample_count', 0)} historical rows.",
                    reason=(
                        f"The active training source is {context.get('training_data_file', 'the configured training dataset')}, "
                        "merged with the baseline financial history before model fitting."
                    ),
                    recommendation="Keep adding clean financial history to strengthen seasonality learning and anomaly separation.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "training_data"},
            )

        if parsed.intent == "metric_explanation":
            metric = parsed.entities.get("metric", "the requested metric")
            metric_explanations = {
                "revenue": "Revenue is the incoming business value recognized from transactions or invoices.",
                "expenses": "Expenses are the outgoing costs associated with operating activity.",
                "expense": "Expenses are the outgoing costs associated with operating activity.",
                "profit": "Profit is revenue minus expenses.",
                "margin": "Margin refers to profit expressed as a percentage of revenue.",
                "cash flow": "Cash flow shows how much cash actually moved, which can differ from booked revenue.",
                "risk probability": "Risk probability is the Bayesian estimate of how likely the current situation is to represent meaningful risk.",
                "risk": "Risk combines anomaly evidence, financial deterioration signals, and model reasoning.",
                "anomaly score": "Anomaly score is the hybrid output from the isolation forest and autoencoder models.",
                "anomaly": "An anomaly is a record that looks materially different from the learned financial baseline.",
            }
            return pack(
                self._format_reasoning(
                    insight=metric_explanations.get(metric, f"{metric.title()} is available in the dashboard context."),
                    reason="I used the metric name in your question to switch into an explanation-style answer instead of a reporting-style answer.",
                    recommendation="Ask for the latest value too if you want both the definition and the current reading.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "metric_explanation", "metric": metric},
            )

        if parsed.intent == "access_control":
            allowed = [name.replace("_", " ") for name, enabled in permissions.items() if enabled]
            return pack(
                self._format_reasoning(
                    insight=f"Your current role is allowed to use: {', '.join(allowed[:8])}{'...' if len(allowed) > 8 else ''}.",
                    reason="Access in this app is role-based, so admins, reviewers, analysts, and viewers do not all see the same modules.",
                    recommendation="If you need something you can’t open, ask an administrator to review your role.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "access_control"},
            )

        uploaded_insights = context.get("insights", [])
        if uploaded_insights and re.search(r"insight|summary|uploaded data", lower):
            return pack(
                self._format_reasoning(
                    insight=uploaded_insights[0],
                    reason="The system generated this from the most recent dataset after preprocessing and feature engineering.",
                    recommendation="Use these uploaded-data insights as a quick validation check before relying on anomaly scores.",
                    context_line=memory_context,
                ),
                "function",
                {"name": "uploaded_insights"},
            )

        if "download" in lower and not permissions.get("download_reports", False):
            return pack(
                self._format_reasoning(
                    insight="Downloads are restricted for your current role.",
                    reason="This account can monitor the live dashboard but cannot export reports or logs.",
                    recommendation="Ask an administrator if you need export privileges.",
                    context_line=memory_context,
                ),
                "restricted",
                {"required_permission": "download_reports"},
            )

        if parsed.intent in {"general_finance_question", "general_question"}:
            return self._answer_general_finance_question(query, context, latest, latest_decision, memory_context)

        return pack(
            self._format_reasoning(
                insight="I didn’t find a precise intent match, but I can still help from the live dashboard context.",
                reason="Your question was broad or phrased differently from my strongest intent patterns, so I’m falling back to a general contextual answer path instead of failing.",
                recommendation="Try rephrasing naturally, for example: 'summarize the current state', 'which invoices are unpaid?', 'compare profit this month with last month', or 'what changed in the latest anomaly?'.",
                context_line=memory_context,
            ),
            "fallback",
            {},
        )
