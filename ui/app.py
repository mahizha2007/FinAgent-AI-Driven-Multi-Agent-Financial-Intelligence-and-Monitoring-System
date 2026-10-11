from __future__ import annotations

import sys
from html import escape as html_escape
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import DATABASE, SERVICE, initialize_scheduler
from ui.auth_ui import logout_user, require_login
from ui.theme import apply_classic_theme
from utils.logger import log_event, read_event_logs
from services.reporting_service import ReportingService
from utils.timezone import now_ist_iso, to_ist_timestamp


st.set_page_config(page_title="Financial Command Center", layout="wide")
REPORTING_SERVICE = ReportingService()


def has_permission(context: dict, permission: str) -> bool:
    """Return whether the current user context has a specific permission."""
    return bool(context.get("permissions", {}).get(permission, False))


def render_permission_notice(title: str, message: str) -> None:
    """Show a consistent restricted-access message."""
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader(title)
    st.warning(message)
    st.markdown("</div>", unsafe_allow_html=True)


def _ensure_chat_state() -> None:
    """Initialize shared chat state."""
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "chat_style" not in st.session_state:
        st.session_state.chat_style = "Operator"


def handle_chat_prompt(context: dict, prompt: str) -> None:
    """Run the chatbot and persist a single prompt/response exchange."""
    if not prompt:
        return
    st.session_state.chat_history.append(("user", prompt))
    context_with_style = {**context, "chat_style": st.session_state.chat_style}
    result = context["chat_interface"].handle_message(prompt, context_with_style)
    st.session_state.chat_history.append(("assistant", result.response.answer))
    log_event(st.session_state.get("authenticated_user", "user"), "chat_prompt", {"prompt": prompt, "style": st.session_state.chat_style})


def render_alert_center(context: dict, username: str) -> None:
    """Show active anomalies until the user acknowledges them."""
    pending_alerts = context["database_manager"].get_unacknowledged_alerts(username, limit=25)
    if not pending_alerts:
        return
    can_acknowledge = has_permission(context, "acknowledge_alerts")

    for alert in pending_alerts:
        st.markdown(
            f"""
            <div class="alert-overlay">
                <div class="alert-title">Active anomaly requires acknowledgement</div>
                <div><strong>{alert['transaction_id']}</strong> | score {alert['anomaly_score']:.2f} | risk {alert['risk_level']} | severity {alert.get('severity', 'INFO')}</div>
                <div style="margin-top:0.35rem;">{alert.get('reasoning_trace', alert.get('explanation', 'Anomaly detected.'))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if can_acknowledge and st.button(f"Acknowledge {alert['transaction_id']}", key=f"ack_{alert['anomaly_id']}"):
            context["database_manager"].acknowledge_alert(alert["anomaly_id"], username)
            log_event(
                username,
                "alert_acknowledged",
                {
                    "anomaly_id": alert["anomaly_id"],
                    "transaction_id": alert["transaction_id"],
                    "severity": alert.get("severity", "INFO"),
                    "acknowledged_at_ist": now_ist_iso(),
                },
            )
            st.rerun()
        elif not can_acknowledge:
            st.caption("Acknowledge permission is restricted for your role.")


def get_preferred_context() -> dict:
    """Load the default or shared-input context on each rerun."""
    initialize_scheduler()
    return SERVICE.build_preferred_context(st.session_state.get("authenticated_user", ""))


def render_hero(context: dict, username: str) -> None:
    """Render the vibrant dashboard header."""
    shared_state = context.get("shared_input_state")
    user_profile = context.get("user_profile", {})
    pending_signups = len(context.get("pending_user_approvals", []))
    source_label = "Default ERP dataset"
    if shared_state and shared_state.get("is_active"):
        source_label = f"Live shared dataset from {shared_state.get('username', 'user')}: {shared_state.get('source_label', 'submission')}"

    st.markdown(
        f"""
        <div class="hero-card">
            <div class="hero-title">Financial Command Center</div>
            <div class="hero-subtitle">
                Welcome, {username}. Unified monitoring for anomalies, risk, explainability, forecasts, simulations, and shared submissions.
            </div>
        </div>
        <div class="status-pill">{source_label}</div>
        <div>
            <span class="kpi-ribbon">Role: {user_profile.get('role', 'viewer').title()}</span>
            <span class="kpi-ribbon">Tenant: {user_profile.get('tenant_name', 'Default Finance')}</span>
            <span class="kpi-ribbon">Training Rows: {context.get('training_sample_count', 0):,}</span>
            {"<span class='kpi-ribbon'>Pending Signups: " + str(pending_signups) + "</span>" if pending_signups and has_permission(context, "manage_users") else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpis(df: pd.DataFrame) -> None:
    """Render top-line KPI cards."""
    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) > 1 else latest
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Latest Revenue", f"{latest['revenue']:,.0f}", delta=f"{latest['revenue'] - previous['revenue']:+,.0f}")
    col2.metric("Latest Expenses", f"{latest['expenses']:,.0f}", delta=f"{latest['expenses'] - previous['expenses']:+,.0f}", delta_color="inverse")
    col3.metric("Anomaly Score", f"{latest['anomaly_score']:.2f}", delta=f"{latest['anomaly_score'] - previous['anomaly_score']:+.2f}", delta_color="inverse")
    col4.metric("Profit", f"{latest['profit']:,.0f}", delta=f"{latest['profit'] - previous['profit']:+,.0f}")


def style_chart(figure, title: str):
    """Apply the shared chart theme."""
    figure.update_layout(
        title=title,
        paper_bgcolor="rgba(255,255,255,0)",
        plot_bgcolor="rgba(255,255,255,0.66)",
        font=dict(color="#1d2a3a"),
        title_font=dict(size=21, color="#162338"),
        margin=dict(l=28, r=20, t=60, b=28),
        legend_title_text="",
    )
    figure.update_xaxes(showgrid=False, linecolor="rgba(29,42,58,0.18)")
    figure.update_yaxes(gridcolor="rgba(29,42,58,0.10)", zeroline=False)
    return figure


def render_overview_tab(context: dict) -> None:
    """Render KPI and chart overview content."""
    df = context["dataframe"]
    chart_df = context.get("chart_dataframe", df)
    comparison_df = context.get("comparison_dataframe", chart_df)
    render_kpis(df)

    active_summary_df = df.copy()
    if "uploaded" in df.columns and bool(df["uploaded"].fillna(False).iloc[-1]):
        active_summary_df = df.copy()
    else:
        active_summary_df = comparison_df.copy()

    total_revenue = float(active_summary_df["revenue"].sum())
    total_expenses = float(active_summary_df["expenses"].sum())
    total_profit = float(active_summary_df["profit"].sum())
    total_losses = float(abs(active_summary_df.loc[active_summary_df["profit"] < 0, "profit"].sum()))
    avg_margin = float(active_summary_df["profit_margin"].mean())
    anomaly_count = int((active_summary_df["anomaly_label"] == 1).sum()) if "anomaly_label" in active_summary_df.columns else 0
    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) > 1 else latest

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Executive Summary")
    summary_scope = "active uploaded dataset" if active_summary_df is df or active_summary_df.equals(df) else "historical comparison dataset"
    st.caption(f"Executive totals below are calculated from the {summary_scope}. Latest-row deltas appear in the KPI cards above.")
    exec_col1, exec_col2, exec_col3, exec_col4 = st.columns(4)
    exec_col1.metric("Total Revenue", f"{total_revenue:,.0f}")
    exec_col2.metric("Total Expenses", f"{total_expenses:,.0f}")
    exec_col3.metric("Total Profit", f"{total_profit:,.0f}")
    exec_col4.metric("Total Losses", f"{total_losses:,.0f}", delta="Contained" if total_losses == 0 else "Watch")

    exec_col5, exec_col6, exec_col7, exec_col8 = st.columns(4)
    exec_col5.metric("Average Margin", f"{avg_margin:.2%}", delta=f"{latest['profit_margin'] - previous['profit_margin']:+.2%}")
    exec_col6.metric("Active Anomalies", f"{anomaly_count}", delta=f"{int(latest['anomaly_label']) - int(previous['anomaly_label']):+d}" if "anomaly_label" in df.columns else "0")
    exec_col7.metric("Risk Level", latest["risk_level"], delta="Escalate" if latest["risk_level"] == "HIGH" else "Stable")
    exec_col8.metric("Training Rows", f"{context.get('training_sample_count', 0):,}", delta="Expanded")
    st.markdown("</div>", unsafe_allow_html=True)

    flow_chart = style_chart(
        go.Figure(
            go.Waterfall(
                name="Financial Flow",
                orientation="v",
                measure=["absolute", "relative", "total", "relative", "total"],
                x=["Revenue", "Expenses", "Net Profit", "Loss Exposure", "Retained"],
                textposition="outside",
                y=[total_revenue, -total_expenses, 0, -total_losses, 0],
                connector={"line": {"color": "rgba(29,42,58,0.25)"}},
                increasing={"marker": {"color": "#0ea5e9"}},
                decreasing={"marker": {"color": "#f97316"}},
                totals={"marker": {"color": "#14b8a6"}},
            )
        ),
        "Revenue to Profit Bridge",
    )
    margin_chart = style_chart(
        px.area(
            comparison_df.assign(margin_pct=comparison_df["profit_margin"] * 100),
            x="date",
            y="margin_pct",
            color_discrete_sequence=["#14b8a6"],
        ),
        "Profit Margin Trend",
    )

    anomaly_chart = style_chart(
        px.line(chart_df, x="date", y="anomaly_score", markers=True, color_discrete_sequence=["#d64c2f"]),
        "Anomaly Timeline",
    )
    trend_chart = style_chart(
        px.line(
            chart_df,
            x="date",
            y=["revenue", "expenses", "profit"],
            color_discrete_sequence=["#1c63b7", "#d64c2f", "#c7942f"],
        ),
        "Financial Trends",
    )
    forecast_chart = style_chart(
        px.line(
            pd.concat(
                [
                    context["revenue_forecast"].assign(series="Revenue Forecast").rename(columns={"ds": "date", "yhat": "forecast"}),
                    context["expense_forecast"].assign(series="Expense Forecast").rename(columns={"ds": "date", "yhat": "forecast"}),
                ],
                ignore_index=True,
            ),
            x="date",
            y="forecast",
            color="series",
            color_discrete_sequence=["#1c63b7", "#ff8a3d"],
        ),
        "Forecast Outlook",
    )

    left, right = st.columns(2)
    with left:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.plotly_chart(anomaly_chart)
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.plotly_chart(trend_chart)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.plotly_chart(forecast_chart)
    st.markdown("</div>", unsafe_allow_html=True)

    extra_left, extra_right = st.columns(2)
    with extra_left:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.plotly_chart(flow_chart)
        st.markdown("</div>", unsafe_allow_html=True)
    with extra_right:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.plotly_chart(margin_chart)
        st.markdown("</div>", unsafe_allow_html=True)

    all_time_df = comparison_df.copy()
    all_time_revenue = float(all_time_df["revenue"].sum())
    all_time_expenses = float(all_time_df["expenses"].sum())
    all_time_profit = float(all_time_df["profit"].sum())
    all_time_profit_margin = (
        all_time_profit / all_time_revenue if abs(all_time_revenue) > 1e-9 else 0.0
    )
    all_time_anomalies = int((all_time_df["anomaly_label"] == 1).sum()) if "anomaly_label" in all_time_df.columns else 0

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("All-Time Performance")
    st.caption("This section uses the full historical comparison dataset so you can monitor lifetime business performance and anomaly behavior.")
    all_time_col1, all_time_col2, all_time_col3, all_time_col4 = st.columns(4)
    all_time_col1.metric("All-Time Revenue", f"{all_time_revenue:,.0f}")
    all_time_col2.metric("All-Time Expenses", f"{all_time_expenses:,.0f}")
    all_time_col3.metric("All-Time Profit Margin", f"{all_time_profit_margin:.2%}")
    all_time_col4.metric("All-Time Anomalies", f"{all_time_anomalies}")
    st.markdown("</div>", unsafe_allow_html=True)

    cumulative_df = all_time_df.sort_values("date").copy()
    cumulative_df["cumulative_revenue"] = cumulative_df["revenue"].cumsum()
    cumulative_df["cumulative_expenses"] = cumulative_df["expenses"].cumsum()
    cumulative_df["cumulative_profit"] = cumulative_df["profit"].cumsum()

    cumulative_chart = style_chart(
        px.line(
            cumulative_df,
            x="date",
            y=["cumulative_revenue", "cumulative_expenses", "cumulative_profit"],
            color_discrete_sequence=["#2563eb", "#f97316", "#14b8a6"],
        ),
        "All-Time Cumulative Revenue, Expenses, and Profit",
    )
    anomaly_distribution = pd.DataFrame(
        [
            {"category": "Anomalies", "count": all_time_anomalies},
            {"category": "Non-Anomalies", "count": max(len(all_time_df) - all_time_anomalies, 0)},
        ]
    )
    anomaly_mix_chart = style_chart(
        px.bar(
            anomaly_distribution,
            x="category",
            y="count",
            color="category",
            color_discrete_sequence=["#dc2626", "#1d4ed8"],
        ),
        "All-Time Anomaly Mix",
    )

    history_left, history_right = st.columns(2)
    with history_left:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.plotly_chart(cumulative_chart)
        st.markdown("</div>", unsafe_allow_html=True)
    with history_right:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.plotly_chart(anomaly_mix_chart)
        st.markdown("</div>", unsafe_allow_html=True)


def render_revenue_compare_tab(context: dict) -> None:
    """Compare revenue across separate time intervals."""
    df = context.get("comparison_dataframe", context["chart_dataframe"]).copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    if df.empty:
        st.info("No dated revenue records are available for comparison.")
        return

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Revenue Compare")
    st.caption("Compare two different time windows to understand revenue status, momentum, and operating change.")

    min_date = df["date"].dt.date.min()
    max_date = df["date"].dt.date.max()
    default_a_start = min_date
    default_a_end = min(max_date, default_a_start.replace(day=min(28, default_a_start.day)) if hasattr(default_a_start, "replace") else max_date)
    first_month_rows = df[df["date"].dt.to_period("M") == df["date"].dt.to_period("M").min()]
    last_month_rows = df[df["date"].dt.to_period("M") == df["date"].dt.to_period("M").max()]
    if not first_month_rows.empty:
        default_a_start = first_month_rows["date"].dt.date.min()
        default_a_end = first_month_rows["date"].dt.date.max()
    default_b_start = max_date
    default_b_end = max_date
    if not last_month_rows.empty:
        default_b_start = last_month_rows["date"].dt.date.min()
        default_b_end = last_month_rows["date"].dt.date.max()

    def normalize_date_state(key: str, fallback, minimum, maximum):
        """Return a safe date value for a widget and persist it into session state."""
        current = st.session_state.get(key)
        if current is None:
            current = fallback
        if hasattr(current, "date"):
            current = current.date()
        if current < minimum or current > maximum:
            current = fallback
        st.session_state[key] = current
        return current

    control_col1, control_col2 = st.columns(2)
    granularity = control_col1.selectbox("Compare by", ["Daily", "Weekly", "Monthly"], index=2)
    metric = control_col2.selectbox("Primary metric", ["revenue", "profit", "expenses"], index=0)

    period_a_start_value = normalize_date_state("period_a_start", default_a_start, min_date, max_date)
    period_b_start_value = normalize_date_state("period_b_start", default_b_start, min_date, max_date)
    period_a_end_default = default_a_end if default_a_end >= period_a_start_value else period_a_start_value
    period_b_end_default = default_b_end if default_b_end >= period_b_start_value else period_b_start_value
    period_a_end_value = normalize_date_state("period_a_end", period_a_end_default, period_a_start_value, max_date)
    period_b_end_value = normalize_date_state("period_b_end", period_b_end_default, period_b_start_value, max_date)

    left_col, right_col = st.columns(2)
    period_a_start = left_col.date_input("Period A start", value=period_a_start_value, min_value=min_date, max_value=max_date, key="period_a_start")
    normalized_a_end = period_a_end_value if period_a_end_value >= period_a_start else period_a_start
    if st.session_state.get("period_a_end") != normalized_a_end:
        st.session_state["period_a_end"] = normalized_a_end
    period_a_end = left_col.date_input("Period A end", value=normalized_a_end, min_value=period_a_start, max_value=max_date, key="period_a_end")

    period_b_start = right_col.date_input("Period B start", value=period_b_start_value, min_value=min_date, max_value=max_date, key="period_b_start")
    normalized_b_end = period_b_end_value if period_b_end_value >= period_b_start else period_b_start
    if st.session_state.get("period_b_end") != normalized_b_end:
        st.session_state["period_b_end"] = normalized_b_end
    period_b_end = right_col.date_input("Period B end", value=normalized_b_end, min_value=period_b_start, max_value=max_date, key="period_b_end")

    period_a = df[(df["date"].dt.date >= period_a_start) & (df["date"].dt.date <= period_a_end)].copy()
    period_b = df[(df["date"].dt.date >= period_b_start) & (df["date"].dt.date <= period_b_end)].copy()

    if period_a.empty or period_b.empty:
        st.warning("Both intervals need at least one record to compare.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    summary_a = {
        "Revenue": float(period_a["revenue"].sum()),
        "Expenses": float(period_a["expenses"].sum()),
        "Profit": float(period_a["profit"].sum()),
        "Avg Anomaly": float(period_a["anomaly_score"].mean()),
    }
    summary_b = {
        "Revenue": float(period_b["revenue"].sum()),
        "Expenses": float(period_b["expenses"].sum()),
        "Profit": float(period_b["profit"].sum()),
        "Avg Anomaly": float(period_b["anomaly_score"].mean()),
    }
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    delta_value = summary_b["Revenue"] - summary_a["Revenue"]
    metric_col1.metric("Period A Revenue", f"{summary_a['Revenue']:,.0f}")
    metric_col2.metric("Period B Revenue", f"{summary_b['Revenue']:,.0f}", delta=f"{delta_value:,.0f}")
    metric_col3.metric("Status Shift", "Improved" if delta_value > 0 else "Declined" if delta_value < 0 else "Flat")

    compare_rows = pd.DataFrame(
        [
            {"period": "Period A", **summary_a},
            {"period": "Period B", **summary_b},
        ]
    )
    compare_chart = style_chart(
        px.bar(
            compare_rows,
            x="period",
            y=["Revenue", "Expenses", "Profit"],
            barmode="group",
            color_discrete_sequence=["#2563eb", "#f97316", "#14b8a6"],
        ),
        "Interval Comparison",
    )
    timeline_source = period_a.assign(interval="Period A").copy()
    timeline_source = pd.concat([timeline_source, period_b.assign(interval="Period B")], ignore_index=True)
    if granularity == "Weekly":
        timeline_source["bucket"] = timeline_source["date"].dt.to_period("W").astype(str)
    elif granularity == "Monthly":
        timeline_source["bucket"] = timeline_source["date"].dt.to_period("M").astype(str)
    else:
        timeline_source["bucket"] = timeline_source["date"].dt.strftime("%Y-%m-%d")
    grouped = timeline_source.groupby(["bucket", "interval"], as_index=False)[metric].sum()
    trend_chart = style_chart(
        px.line(grouped, x="bucket", y=metric, color="interval", markers=True, color_discrete_sequence=["#2563eb", "#14b8a6"]),
        f"{metric.title()} Status Across Intervals",
    )

    chart_col1, chart_col2 = st.columns(2)
    chart_col1.plotly_chart(compare_chart)
    chart_col2.plotly_chart(trend_chart)
    st.dataframe(compare_rows, width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)


def render_intelligence_tab(context: dict) -> None:
    """Render decision intelligence, anomalies, and governance signals."""
    df = context["dataframe"]
    latest_decision = context.get("latest_decision", {})
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Basic Financial Insights")
    for insight in context.get("insights", []):
        st.write(f"- {insight}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Decision Intelligence")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Decision", latest_decision.get("decision", df.iloc[-1].get("decision", "N/A")))
    col2.metric("Risk Probability", f"{latest_decision.get('risk_probability', 0.0):.2f}")
    col3.metric("Decision Confidence", f"{latest_decision.get('confidence_score', 0.0):.2f}")
    col4.metric("Consensus Confidence", f"{latest_decision.get('consensus_confidence', 0.0):.2f}")
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Uncertainty", f"{latest_decision.get('uncertainty', 0.0):.2f}")
    col6.metric("Final Score", f"{latest_decision.get('final_score', 0.0):.2f}")
    col7.metric("Financial Impact", f"{latest_decision.get('financial_impact', 0.0):,.0f}")
    col8.metric("Email Alerts", "Enabled" if context.get("email_alert_enabled") else "Disabled")
    st.write("Reasoning Trace")
    st.code(latest_decision.get("reasoning_trace", "No decision trace available."), language="text")
    st.write(f"Recommended Action: {latest_decision.get('recommended_action', 'No recommendation available.')}")
    st.write(f"Impact Chain: {latest_decision.get('impact_chain', 'No impact chain available.')}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("Flagged Transactions")
    flagged_columns = [
        "date",
        "transaction_id",
        "revenue",
        "expenses",
        "profit",
        "anomaly_score",
        "risk_level",
        "risk_probability",
        "decision",
        "zscore_anomaly",
    ]
    available_flagged_columns = [column for column in flagged_columns if column in df.columns]
    st.dataframe(
        df[df["anomaly_label"] == 1][available_flagged_columns],
        width="stretch",
    )

    st.subheader("Active Alerts")
    alerts = [alert for alert in context["alerts"] if alert["decision"] == "ALERT"]
    if alerts:
        for alert in alerts:
            st.error(
                f"{alert['transaction_id']} | score={alert['anomaly_score']:.2f} | "
                f"risk={alert['risk_level']} | {alert['explanation']}"
            )
    else:
        st.success("No active high-severity alerts.")

    st.subheader("Alert History")
    decision_history = pd.DataFrame(context.get("decision_history", []))
    if decision_history.empty:
        st.info("No decision history available yet.")
    else:
        st.dataframe(decision_history, width="stretch")

    st.subheader("Model Governance")
    model_versions = pd.DataFrame(context.get("model_versions", []))
    if model_versions.empty:
        st.info("No model version records available yet.")
    else:
        st.dataframe(model_versions, width="stretch")


def render_operating_system_tab(context: dict) -> None:
    """Render financial operating system intelligence panels."""
    if not has_permission(context, "view_operating_system"):
        render_permission_notice("Operating System", "Your current role can view the executive dashboard but not the detailed operating-system intelligence panels.")
        return
    health_score = context["health_score"]
    cash_flow = context["cash_flow_intelligence"]
    budget = context["budget_variance"]
    optimization = context["cost_optimization"]
    exposure = context["risk_exposure"]
    loan_credit = context["loan_credit"]

    score_gauge = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=health_score.score,
            title={"text": f"Financial Health Score ({health_score.status})"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#0ea5e9"},
                "steps": [
                    {"range": [0, 40], "color": "#fee2e2"},
                    {"range": [40, 70], "color": "#fef3c7"},
                    {"range": [70, 100], "color": "#dcfce7"},
                ],
            },
        )
    )
    score_gauge = style_chart(score_gauge, "Financial Health")

    exposure_chart = style_chart(
        px.bar(
            pd.DataFrame(
                [
                    {"category": "Operational", "amount": exposure.operational_exposure},
                    {"category": "Revenue", "amount": exposure.revenue_exposure},
                    {"category": "Cost", "amount": exposure.cost_exposure},
                ]
            ),
            x="category",
            y="amount",
            color="category",
            color_discrete_sequence=["#0ea5e9", "#f97316", "#14b8a6"],
        ),
        "Risk Exposure by Category",
    )

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Financial Operating System")
    row1 = st.columns(4)
    row1[0].metric("Runway", f"{cash_flow.runway_months:.2f} months", delta=cash_flow.liquidity_risk)
    row1[1].metric("Budget Profit Variance", f"{budget.profit_variance:,.0f}", delta=f"{budget.revenue_variance:,.0f} revenue")
    row1[2].metric("Savings Potential", f"{optimization.estimated_savings:,.0f}", delta="Optimize")
    row1[3].metric("Total Exposure", f"{exposure.total_exposure:,.0f}", delta="Monitor")
    row2 = st.columns(4)
    row2[0].metric("EMI Capacity", f"{loan_credit.emi_capacity:,.0f}")
    row2[1].metric("Estimated Credit Score", f"{loan_credit.estimated_credit_score}")
    row2[2].metric("Default Risk", f"{loan_credit.default_risk:.2f}")
    row2[3].metric("Optimal Loan Limit", f"{loan_credit.optimal_loan_limit:,.0f}")
    st.write(cash_flow.summary)
    st.write(budget.summary)
    st.write(exposure.summary)
    st.markdown("</div>", unsafe_allow_html=True)

    left, right = st.columns(2)
    with left:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.plotly_chart(score_gauge)
        st.write("Health Breakdown")
        st.dataframe(pd.DataFrame([health_score.breakdown]), width="stretch")
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.plotly_chart(exposure_chart)
        st.write("Cost Optimization Drivers")
        for driver in optimization.drivers:
            st.write(f"- {driver}")
        st.write(f"Recommendation: {optimization.recommendation}")
        st.markdown("</div>", unsafe_allow_html=True)


def render_governance_tab(context: dict) -> None:
    """Render governance, workflow, approvals, and memory artifacts."""
    if not has_permission(context, "view_governance"):
        render_permission_notice("Governance", "Governance, workflow, approvals, and agent trace records are restricted to elevated roles.")
        return
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Governance & Workflow")
    latest_decision = context.get("latest_decision", {})
    st.write(f"Policy Rationale: {latest_decision.get('policy_rationale', 'No policy rationale available.')}")
    flags = latest_decision.get("policy_flags", [])
    if flags:
        for flag in flags:
            st.write(f"- {flag}")
    else:
        st.write("- No active policy escalations.")
    st.markdown("</div>", unsafe_allow_html=True)

    tasks_df = pd.DataFrame(context.get("tasks", []))
    approvals_df = pd.DataFrame(context.get("approvals", []))
    agent_outputs_df = pd.DataFrame(context.get("agent_outputs", []))
    memory_feedback_df = pd.DataFrame(context.get("memory_feedback", []))

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Tasks")
        if tasks_df.empty:
            st.info("No workflow tasks yet.")
        else:
            st.dataframe(tasks_df, width="stretch")
        st.markdown("</div>", unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Approvals")
        if approvals_df.empty:
            st.info("No approval steps yet.")
        else:
            st.dataframe(approvals_df, width="stretch")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Agent Output Trace")
    if agent_outputs_df.empty:
        st.info("No agent output trace records yet.")
    else:
        st.dataframe(agent_outputs_df, width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Adaptive Memory Feedback")
    if memory_feedback_df.empty:
        st.info("No memory feedback logged yet.")
    else:
        st.dataframe(memory_feedback_df, width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)


def render_access_security_tab(context: dict, username: str) -> None:
    """Render access-control and security administration panels."""
    can_manage_users = has_permission(context, "manage_users")
    can_manage_security = has_permission(context, "manage_security")
    if not can_manage_users and not can_manage_security:
        render_permission_notice("Access & Security", "Only administrators can manage user access and security controls.")
        return

    database_manager = context["database_manager"]
    users_df = pd.DataFrame(context.get("security_users", []))
    login_attempts_df = pd.DataFrame(context.get("login_attempts", []))
    pending_user_approvals_df = pd.DataFrame(context.get("pending_user_approvals", []))

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Access & Security")
    top_col1, top_col2, top_col3, top_col4 = st.columns(4)
    top_col1.metric("Active Users", f"{int(users_df['is_active'].sum()) if not users_df.empty else 0}")
    top_col2.metric("Locked Users", f"{int(users_df['locked_until'].fillna('').astype(str).str.len().gt(0).sum()) if not users_df.empty else 0}")
    top_col3.metric("Failed Attempts", f"{int(users_df['failed_login_count'].fillna(0).sum()) if not users_df.empty else 0}")
    top_col4.metric("Pending Signups", f"{len(pending_user_approvals_df)}", delta="Review" if not pending_user_approvals_df.empty else "Clear")
    st.caption("Security controls now include password-strength checks, login-attempt auditing, timed session expiry, and temporary lockout after repeated failures.")
    st.markdown("</div>", unsafe_allow_html=True)

    if can_manage_users:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Registration Approval Queue")
        if pending_user_approvals_df.empty:
            st.success("No pending self-service registrations.")
        else:
            st.warning(f"{len(pending_user_approvals_df)} new user request(s) are waiting for admin approval.")
            st.dataframe(pending_user_approvals_df, width="stretch", height=220)
            selected_pending_user = st.selectbox(
                "Pending user",
                pending_user_approvals_df["username"].tolist(),
                key="pending_user_select",
            )
            queue_col1, queue_col2 = st.columns(2)
            if queue_col1.button("Approve Selected User", key="approve_pending_user"):
                success, message = database_manager.resolve_user_registration(selected_pending_user, approved=True, actor=username)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
            if queue_col2.button("Reject Selected User", key="reject_pending_user"):
                success, message = database_manager.resolve_user_registration(selected_pending_user, approved=False, actor=username)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
        st.markdown("</div>", unsafe_allow_html=True)

    if can_manage_users:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("User Directory")
        if users_df.empty:
            st.info("No user records are available.")
        else:
            display_users = users_df.copy()
            if "is_active" in display_users.columns:
                display_users["is_active"] = display_users["is_active"].astype(bool)
            st.dataframe(display_users, width="stretch", height=320)

            usernames = display_users["username"].tolist()
            selected_username = st.selectbox("Select user", usernames, key="access_selected_user")
            selected_row = display_users[display_users["username"] == selected_username].iloc[0]
            is_default_admin = str(selected_username).strip().lower() == "admin"
            admin_col1, admin_col2 = st.columns(2)
            with admin_col1.form("update_user_access_form", clear_on_submit=False):
                available_roles = SERVICE.access_control.list_roles()
                fixed_role = "admin" if is_default_admin else selected_row["role"]
                new_role = st.selectbox(
                    "Role",
                    available_roles,
                    index=available_roles.index(fixed_role) if fixed_role in available_roles else len(available_roles) - 1,
                    disabled=is_default_admin,
                )
                is_active = st.checkbox("Account active", value=True if is_default_admin else bool(selected_row["is_active"]), disabled=is_default_admin)
                if is_default_admin:
                    st.caption("The default admin account is protected and cannot be demoted or deactivated.")
                update_submitted = st.form_submit_button("Save Access Changes", disabled=is_default_admin)
            if update_submitted:
                role_success, role_message = database_manager.update_user_role(selected_username, new_role, username)
                status_success, status_message = database_manager.set_user_active(selected_username, is_active, username)
                if role_success and status_success:
                    st.success("User access updated.")
                    st.rerun()
                else:
                    st.error(" | ".join(message for ok, message in [(role_success, role_message), (status_success, status_message)] if not ok))

            with admin_col2.form("create_admin_user_form", clear_on_submit=True):
                st.markdown("**Create Managed Account**")
                new_username = st.text_input("Username")
                new_password = st.text_input("Temporary Password", type="password")
                new_role = st.selectbox("Assigned role", SERVICE.access_control.list_roles(), index=3, key="create_role")
                create_user_submitted = st.form_submit_button("Create User")
            if create_user_submitted:
                success, message = database_manager.create_user(new_username, new_password, role=new_role, created_by=username)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
        st.markdown("</div>", unsafe_allow_html=True)

    if can_manage_security:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Security Monitoring")
        if login_attempts_df.empty:
            st.info("No login attempts recorded yet.")
        else:
            st.dataframe(login_attempts_df, width="stretch", height=280)

        locked_users = users_df[users_df["locked_until"].fillna("").astype(str).str.len() > 0] if not users_df.empty else pd.DataFrame()
        if locked_users.empty:
            st.success("No accounts are currently locked.")
        else:
            unlock_user = st.selectbox("Unlock account", locked_users["username"].tolist(), key="unlock_user_select")
            if st.button("Unlock Selected User", key="unlock_user_button"):
                success, message = database_manager.unlock_user(unlock_user, username)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
        st.markdown("</div>", unsafe_allow_html=True)


def render_explainability_tab(context: dict) -> None:
    """Render SHAP explainability tools."""
    if not has_permission(context, "view_explainability"):
        render_permission_notice("Explainability", "Detailed explainability is available only to analyst and admin roles.")
        return
    anomaly_rows = context["dataframe"][context["dataframe"]["anomaly_label"] == 1]
    if anomaly_rows.empty:
        st.info("No anomalies detected in the current run.")
        return
    selected_txn = st.selectbox("Select flagged transaction", anomaly_rows["transaction_id"].tolist())
    selected_index = anomaly_rows.index[anomaly_rows["transaction_id"] == selected_txn][0]
    explanation = context["explanation_agent"].run(context["feature_matrix"][selected_index:selected_index + 1])
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.write(explanation.explanation_text)
    st.dataframe(pd.DataFrame(explanation.top_features, columns=["Feature", "SHAP Impact"]), width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)


def render_simulation_tab(context: dict, username: str) -> None:
    """Render scenario simulation controls."""
    if not has_permission(context, "run_scenarios"):
        render_permission_notice("Scenario Lab", "Stress testing and custom scenario generation are restricted to analyst and admin roles.")
        return
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Scenario Lab")
    builtin_scenarios = context["simulation_agent"].get_builtin_scenarios()
    builtin_names = [scenario["name"] for scenario in builtin_scenarios]
    selected_name = st.selectbox("Built-in scenarios", builtin_names)
    selected_scenario = next(item for item in builtin_scenarios if item["name"] == selected_name)
    col1, col2 = st.columns(2)
    if col1.button("Run Built-in Scenario", key="run_builtin_scenario"):
        result = context["simulation_agent"].run(
            latest_record=context["dataframe"].iloc[-1],
            revenue_drop_pct=float(selected_scenario["revenue_drop_pct"]),
            expense_increase_pct=float(selected_scenario["expense_increase_pct"]),
            scenario_text=str(selected_scenario["name"]),
        )
        log_event(username, "stress_test_builtin", selected_scenario)
        st.success(
            f"{selected_name}: stressed profit {result.result.stressed_profit:,.0f} | "
            f"impact {result.result.profit_impact:,.0f} | risk {result.result.risk_score:.2f}"
        )

    st.write("Custom Scenario Generator")
    col3, col4, col5 = st.columns(3)
    max_revenue_drop = col3.slider("Max revenue drop %", min_value=0, max_value=50, value=20, step=5)
    max_expense_increase = col4.slider("Max expense increase %", min_value=0, max_value=50, value=15, step=5)
    scenario_count = col5.slider("Generated scenarios", min_value=3, max_value=10, value=5, step=1)
    generated_scenarios = context["simulation_agent"].generate_custom_scenarios(
        max_revenue_drop_pct=max_revenue_drop / 100.0,
        max_expense_increase_pct=max_expense_increase / 100.0,
        count=scenario_count,
    )
    st.dataframe(pd.DataFrame(generated_scenarios), width="stretch")
    if st.button("Run Generated Scenario Set", key="run_generated_scenarios"):
        rows = []
        for scenario in generated_scenarios:
            result = context["simulation_agent"].run(
                latest_record=context["dataframe"].iloc[-1],
                revenue_drop_pct=float(scenario["revenue_drop_pct"]),
                expense_increase_pct=float(scenario["expense_increase_pct"]),
                scenario_text=str(scenario["name"]),
            )
            rows.append(
                {
                    "scenario": scenario["name"],
                    "stressed_profit": result.result.stressed_profit,
                    "profit_impact": result.result.profit_impact,
                    "risk_score": result.result.risk_score,
                }
            )
        log_event(username, "stress_test_generated", {"count": len(rows)})
        st.dataframe(pd.DataFrame(rows), width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)

    latest_decision = context.get("latest_decision", {})
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Impact Visualization")
    nodes = context.get("impact_nodes", [])
    edges = context.get("impact_edges", [])
    if nodes and edges:
        x_positions = {node["metric"]: index for index, node in enumerate(nodes)}
        figure = go.Figure()
        for start, end in edges:
            figure.add_trace(
                go.Scatter(
                    x=[x_positions[start], x_positions[end]],
                    y=[1, 1],
                    mode="lines",
                    line=dict(color="#ff8a3d", width=3),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
        figure.add_trace(
            go.Scatter(
                x=[x_positions[node["metric"]] for node in nodes],
                y=[1] * len(nodes),
                mode="markers+text",
                text=[f"{node['metric']}<br>{node['value']:,.0f}" for node in nodes],
                textposition="top center",
                marker=dict(size=28, color="#1c63b7"),
                showlegend=False,
            )
        )
        figure.update_layout(
            height=280,
            margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor="rgba(255,255,255,0)",
            plot_bgcolor="rgba(255,255,255,0)",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
        )
        st.plotly_chart(figure)
    st.write(latest_decision.get("impact_chain", "No impact chain available."))
    st.write(latest_decision.get("counterfactual_summary", "No counterfactual summary available."))
    st.markdown("</div>", unsafe_allow_html=True)


def render_chat_tab(context: dict) -> None:
    """Render the chatbot experience."""
    if not has_permission(context, "use_chat"):
        render_permission_notice("Financial Copilot", "Chat access is restricted for your role.")
        return
    _ensure_chat_state()

    st.markdown('<div id="chat-assistant-panel"></div>', unsafe_allow_html=True)
    st.subheader("Financial Copilot")
    st.markdown('<div class="insight-banner">Ask finance questions, compare periods, review logs, or even ask who the copilot is. Off-topic prompts are handled gracefully too.</div>', unsafe_allow_html=True)
    left, right = st.columns([1, 2])
    with left:
        st.markdown('<div class="chat-panel">', unsafe_allow_html=True)
        st.markdown('<div class="chat-panel-title">Copilot Controls</div>', unsafe_allow_html=True)
        st.session_state.chat_style = st.radio(
            "Choose style",
            ["Operator", "Boardroom", "Pulse"],
            index=["Operator", "Boardroom", "Pulse"].index(st.session_state.chat_style),
            horizontal=True,
            label_visibility="collapsed",
        )
        quick_prompts = [
            "Who are you?",
            "What is the latest decision?",
            "What is the risk probability?",
            "Compare January revenue with March revenue",
            "Show logs",
            "How much training data do you use?",
        ]
        for index, item in enumerate(quick_prompts):
            if st.button(item, key=f"quick_prompt_{index}"):
                st.session_state["pending_prompt"] = item
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown(
            """
            <div class="prompt-card">
                <strong>Copilot Modes</strong><br><br>
                <strong>Operator</strong>: practical and action-first<br>
                <strong>Boardroom</strong>: crisp executive language<br>
                <strong>Pulse</strong>: fast, trendy signal-style output<br><br>
                <strong>Also handles</strong>: identity questions and non-financial prompts with graceful redirection.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-card"><div class="chat-wrap">', unsafe_allow_html=True)
    for speaker, message in st.session_state.chat_history:
        with st.chat_message(speaker):
            st.write(message)
    st.markdown("</div></div>", unsafe_allow_html=True)

    pending_prompt = st.session_state.pop("pending_prompt", None)
    prompt = st.chat_input("Ask about anomalies, risk, forecasts, shared inputs, scenarios, or XIRR")
    final_prompt = pending_prompt or prompt
    if final_prompt:
        handle_chat_prompt(context, final_prompt)
        st.rerun()


def render_command_brief_tab(context: dict, username: str) -> None:
    """Render downloadable master draft content."""
    pdf_bytes = REPORTING_SERVICE.build_master_draft_pdf(context, username)
    csv_bytes = REPORTING_SERVICE.build_master_draft_csv(context, username)
    can_download = has_permission(context, "download_reports")
    st.markdown('<div class="master-draft">', unsafe_allow_html=True)
    st.subheader("Master Draft")
    st.write("A downloadable command brief built from the live decision context, available only as PDF or CSV.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    latest_decision = context.get("latest_decision", {})
    st.write(f"Generated for {username} in IST from the current live dashboard state.")
    st.write(f"Latest decision: {latest_decision.get('decision', 'N/A')}")
    st.write(f"Risk probability: {latest_decision.get('risk_probability', 0.0):.2f}")
    st.write(f"Financial impact: {latest_decision.get('financial_impact', 0.0):,.0f}")
    download_col1, download_col2 = st.columns(2)
    pdf_clicked = download_col1.download_button(
        "Download Master Draft PDF",
        data=pdf_bytes,
        file_name="financial_master_draft.pdf",
        mime="application/pdf",
        disabled=not can_download,
    )
    csv_clicked = download_col2.download_button(
        "Download Master Draft CSV",
        data=csv_bytes,
        file_name="financial_master_draft.csv",
        mime="text/csv",
        disabled=not can_download,
    )
    if pdf_clicked:
        log_event(username, "download_master_draft_pdf", {"rows": len(context.get("dataframe", []))})
    if csv_clicked:
        log_event(username, "download_master_draft_csv", {"rows": len(context.get("dataframe", []))})
    if not can_download:
        st.caption("Downloads are restricted for your role.")
    st.markdown("</div>", unsafe_allow_html=True)


def build_manual_lines(context: dict, username: str) -> list[str]:
    """Build a detailed user manual as line-based content for PDF export."""
    latest_decision = context.get("latest_decision", {})
    training_rows = context.get("training_sample_count", 0)
    shared_state = context.get("shared_input_state") or {}
    latest_source = shared_state.get("source_label", "Default ERP dataset") if shared_state.get("is_active") else "Default ERP dataset"
    return [
        f"Prepared for: {username}",
        f"Generated at: {now_ist_iso()} IST",
        "",
        "1. Product Overview:",
        "This software is an AI-driven financial operating system that ingests financial records, engineers business features, detects anomalies, estimates risk, forecasts future trends, runs scenario simulations, and explains findings through a live chatbot.",
        f"It currently trains against a merged baseline of {training_rows} rows and evaluates the active dataset against that baseline rather than scoring records in isolation.",
        f"The current active source in the dashboard is: {latest_source}.",
        "",
        "2. Core Workflow:",
        "FLOWCHART: Data Ingestion -> Validation & Sanitization -> Feature Engineering -> Hybrid Anomaly Scoring -> Risk & Decision Logic -> Dashboard, Logs, Alerts, and Chatbot",
        "Step 1: Financial data enters through the default dataset, uploaded structured files, unstructured invoice text or PDFs, or manual entry.",
        "Step 2: The preprocessing pipeline cleans missing values, normalizes numeric fields, computes engineered metrics such as revenue growth, expense ratio, and profit margin, and prepares model-ready features.",
        "Step 3: Isolation Forest and the autoencoder score each row. Their outputs are combined into a hybrid anomaly score between 0 and 1.",
        "Step 4: Risk logic, Bayesian probability, policy rules, workflow orchestration, and decision intelligence convert model output into ALERT, INVESTIGATE, or IGNORE.",
        "Step 5: Results are written into the dashboard, logs, alerts, SQLite history, and MySQL mirrors where configured.",
        "• The system is intentionally layered so that model output is not treated as the final truth without business context.",
        "• This means the same record can be moderated or escalated by business rules depending on payment status, receivables, and policy thresholds.",
        "",
        "3. Tab Reference:",
        "Overview: Executive KPIs, anomaly timeline, financial trends, forecast outlook, revenue-to-profit bridge, and profit margin trend.",
        "Revenue Compare: Compare two date windows across revenue, expenses, profit, and average anomaly behavior.",
        "Decision Intelligence: Decision, confidence, Bayesian risk probability, reasoning trace, consensus score, recommendation, and impact summary.",
        "Operating System: Cash flow intelligence, budget vs actual, cost optimization, health score, risk exposure, loan-credit outputs, and workflow-related operating metrics.",
        "Governance: Tasks, approvals, agent outputs, and audit-oriented orchestration records for traceability.",
        "Access & Security: Role management, account state, pending approvals, and login/security activity for administrators.",
        "Explainability: Explains why a record was flagged and shows the dominant feature contributions behind the score.",
        "Scenario Lab: Built-in and generated stress scenarios for revenue drops, expense increases, and profit impact analysis.",
        "Chat Assistant: Natural-language interface for asking questions about decisions, anomalies, forecasts, roles, logs, invoices, and general finance concepts.",
        "Command Brief: Downloadable report outputs in PDF or CSV format.",
        "Manual & Instructions: In-app guide that explains the product, metrics, charts, roles, and usage patterns.",
        "",
        "4. Terminology Guide:",
        "Revenue: Incoming business value recognized from invoices or transactions.",
        "Expenses: Costs associated with servicing or generating that revenue.",
        "Profit: Revenue minus expenses.",
        "Profit Margin: Profit divided by revenue. It measures efficiency of earnings.",
        "Expense Ratio: Expenses divided by revenue. Higher values usually mean margin pressure.",
        "Anomaly Score: A model-combined score from 0 to 1 describing how unusual a record is compared with trained history.",
        "Anomaly Label: A binary flag indicating whether the anomaly score crossed the operating threshold.",
        "Risk Probability: Bayesian probability of risk after combining anomaly signal, forecast risk, and historical frequency.",
        "Consensus Confidence: Agreement strength across the analytical agents.",
        "Counterfactual Impact: The difference between expected financial outcome and actual observed outcome.",
        "",
        "5. Explainability and SHAP:",
        "FLOWCHART: Scored Record -> Explanation Agent -> Heuristic or SHAP Path -> Top Feature Contributions -> Human-readable Explanation",
        "Explainability answers the question: why did the system think this record was unusual?",
        "The Explanation Agent supports two modes.",
        "Mode A: A fast heuristic explanation that ranks the largest feature magnitudes when SHAP is unavailable or intentionally skipped for speed.",
        "Mode B: SHAP-based explanation when the SHAP dependency is available. SHAP estimates each feature's contribution to the anomaly output and surfaces the top drivers.",
        "Typical top drivers include revenue_growth, expense_ratio, profit_margin, accounts_receivable, customer_count, or cash_flow depending on the row.",
        "A larger SHAP impact means that feature contributed more strongly to the anomaly score. SHAP is an explanation layer, not a business rule by itself.",
        "If SHAP is not installed or not active, the system falls back safely to heuristic explanations instead of crashing.",
        "• In practical terms, SHAP helps the user understand why the model reacted, while the decision engine helps the user understand what action to take next.",
        "",
        "6. Chart Guide:",
        "Anomaly Timeline: Shows anomaly score over time so spikes and clusters are easy to identify.",
        "Financial Trends: Plots revenue, expenses, and profit together to show business movement and divergence.",
        "Forecast Outlook: Uses Prophet to estimate near-future revenue and expense behavior.",
        "Revenue to Profit Bridge: Waterfall-style summary from total revenue through expenses and retained result.",
        "Profit Margin Trend: Shows changes in profit efficiency over time.",
        "Impact Visualization: Displays the propagation chain between revenue, profit, cash flow, and risk.",
        "",
        "7. Input Modes:",
        "Structured File: Accepts CSV, JSON, and TXT files with recognizable financial columns.",
        "Unstructured Text: Parses invoice-style text and text-based PDFs to extract invoice ID, date, totals, paid amount, outstanding amount, and payment status.",
        "Manual Entry: Restricted to today's date, auto-generates locked transaction IDs, and increments from the latest MANUAL sequence.",
        "Manual and uploaded records are validated before being promoted to the shared dashboard dataset.",
        "",
        "8. Alerts and Decisions:",
        "ALERT means the record should be surfaced prominently and may trigger email alerts depending on configuration.",
        "INVESTIGATE means the record deserves review but is not necessarily critical.",
        "IGNORE means the record is acceptable after the model and policy review layers are applied.",
        "Unacknowledged ALERT records persist and reappear for the user at login until they are acknowledged.",
        "",
        "9. Roles and Security:",
        "Admin: Full access to dashboard, logs, explainability, scenarios, governance, access control, user approval, and alert settings.",
        "Viewer: Read-only access to the dashboard and limited interactive features.",
        "New users remain pending until an admin approves them. Login attempts, user actions, alerts, and important events are logged for auditability.",
        "• Role restrictions are enforced in both the UI and backend context assembly, not only by hiding tabs.",
        "",
        "10. Storage and Databases:",
        "SQLite stores the application's primary local state, including users, logs, anomalies, decisions, approvals, tasks, and memory feedback.",
        "MySQL mirrors key operational data such as ingested financial rows and application logs so they can be viewed externally.",
        "The table financial_monitor.ingested_financial_data contains baseline training rows and future shared submissions.",
        "The table financial_monitor.logs stores mirrored application events such as navigation, chat, uploads, downloads, login attempts, and errors.",
        "",
        "11. Current Example Snapshot:",
        f"Latest decision: {latest_decision.get('decision', 'N/A')}",
        f"Latest risk probability: {latest_decision.get('risk_probability', 0.0):.2f}",
        f"Latest confidence score: {latest_decision.get('confidence_score', 0.0):.2f}",
        f"Latest financial impact: {latest_decision.get('financial_impact', 0.0):,.0f}",
        f"Recommended action: {latest_decision.get('recommended_action', 'No recommendation available.')}",
        "",
        "12. Troubleshooting:",
        "If a record looks incorrectly anomalous, check whether it is extremely small or large compared with the baseline, whether receivables are outstanding, and whether payment status indicates partial or unpaid behavior.",
        "If unstructured invoice parsing fails, inspect the extracted text preview to confirm the PDF is text-based rather than scanned image-only.",
        "If SHAP outputs are unavailable, install the SHAP dependency and restart the app.",
        "If dashboard or log history looks stale, refresh the app and verify the shared dataset source ribbon at the top of the page.",
        "",
        "13. Screenshot Notes:",
        "The in-app manual includes visual screen previews for the main dashboard, Command Deck, and Data Input Studio to help users orient themselves.",
    ]


def build_technical_manual_lines(context: dict, username: str) -> list[str]:
    """Build an in-depth technical manual describing the full internal logic and math."""
    latest_decision = context.get("latest_decision", {})
    training_rows = context.get("training_sample_count", 0)
    email_enabled = "Yes" if context.get("email_alert_enabled") else "No"
    return [
        f"Prepared for: {username}",
        f"Generated at: {now_ist_iso()} IST",
        "",
        "Technical Logic and Algorithm Manual:",
        "This document explains the mathematical, algorithmic, and control-flow logic of the financial monitoring system in detail.",
        "It is intended as an internal understanding guide and can be removed later without changing the software pipeline itself.",
        "",
        "1. System Architecture:",
        "The system is organized into data ingestion, preprocessing, model scoring, business rule adjustment, risk estimation, decision intelligence, workflow orchestration, explainability, reporting, and persistence layers.",
        "The MonitoringService acts as the orchestration hub. It loads the preferred dataset, pulls or builds training artifacts, transforms current input using the training scaler, runs agent modules, logs outcomes, and returns a unified context to the dashboard and chatbot.",
        f"The current training baseline size exposed to the app is {training_rows} rows.",
        "FLOWCHART: Input Sources -> MonitoringService -> Training Artifact Cache -> Preprocessing -> Model Agents -> Policy & Workflow Engines -> Persistence -> Dashboard and Chat",
        "",
        "2. Ingestion Logic:",
        "Data enters through four main routes: default CSV baseline, shared uploaded structured files, unstructured invoice-like text or PDFs, and manual entry.",
        "Structured input accepts CSV, JSON, and TXT tables. Unstructured input attempts to parse invoice identifiers, dates, totals, paid amount, balance, and payment status from text-based documents.",
        "Manual entry is constrained to today's date and auto-generates MANUAL transaction identifiers by scanning the latest known manual sequence and incrementing from it.",
        "Shared inputs are persisted locally and mirrored into MySQL. Training baseline rows are also mirrored into MySQL under the training baseline source label.",
        "• The ingestion layer is designed to converge every input path into the same canonical dataframe schema so downstream logic stays consistent.",
        "",
        "3. Preprocessing Pipeline:",
        "FLOWCHART: Raw Data -> Required Column Check -> Date Parsing -> Numeric Coercion -> Missing Value Fill -> Feature Engineering -> Scaling",
        "The preprocessing layer first ensures required columns exist: date, transaction_id, revenue, expenses, cash_flow, customer_count, accounts_receivable, inventory, and marketing_spend.",
        "Blank values are normalized to missing values. Dates are parsed to timestamps. If dates are entirely missing, a fallback date range is generated.",
        "Numeric columns are coerced to numeric type. Missing numeric values are filled with the column median when possible and otherwise with zero.",
        "Transaction IDs are cleaned and auto-filled only where absolutely necessary for safety.",
        "The engineered features added by engineer_financial_features are:",
        "profit = revenue - expenses",
        "revenue_growth = revenue.pct_change()",
        "expense_ratio = expenses / revenue",
        "profit_margin = profit / revenue",
        "These features, together with the original financial fields, become the feature vector used by the anomaly models.",
        "",
        "4. Feature Space Used by the Models:",
        "The feature vector is composed of:",
        "revenue, expenses, cash_flow, customer_count, accounts_receivable, inventory, marketing_spend, profit, revenue_growth, expense_ratio, profit_margin",
        "Before model fitting or inference, this feature frame is standardized using StandardScaler, which transforms each feature approximately as z = (x - mean) / std based on the training data fit.",
        "This means inference data is always compared inside the same normalized feature space that the baseline was trained on.",
        "",
        "5. Isolation Forest Logic:",
        "The IsolationForestModel uses contamination=0.12, random_state=42, and n_estimators=200.",
        "Isolation Forest isolates outliers by recursively partitioning the feature space. Records that are easier to isolate are treated as more anomalous.",
        "The implementation converts sklearn score_samples output into an anomaly signal by negating it:",
        "anomaly_signal = - score_samples(features)",
        "The training-time minimum and maximum anomaly signal values are stored.",
        "During inference, the raw anomaly signal is normalized against the training range as:",
        "normalized_iforest = clip((signal - train_min) / (train_max - train_min), 0, 1)",
        "Labels are generated from sklearn's built-in prediction where -1 maps to anomaly_label 1.",
        "• Isolation Forest is valuable here because it does not require labeled anomalies and can work directly from the structure of the normalized feature space.",
        "",
        "6. Autoencoder Logic:",
        "The autoencoder is a PyTorch feed-forward reconstruction model.",
        "Encoder: Linear(input_dim -> hidden_dim), ReLU, Linear(hidden_dim -> bottleneck_dim), ReLU",
        "Decoder: Linear(bottleneck_dim -> hidden_dim), ReLU, Linear(hidden_dim -> input_dim)",
        "hidden_dim is max(4, input_dim * 2); bottleneck_dim is max(2, input_dim // 2).",
        "The model is trained with Adam, learning rate 0.001, mean squared reconstruction loss, default 60 epochs in the current service path, and batch size 8.",
        "After fitting, reconstruction errors are computed per row as the mean squared difference between input and reconstruction.",
        "The anomaly threshold is set at the 0.88 quantile of training reconstruction errors.",
        "During inference:",
        "reconstruction_error = mean((reconstructed - input)^2)",
        "normalized_autoencoder = clip((error - train_error_min) / (train_error_max - train_error_min), 0, 1)",
        "Rows above the trained quantile threshold are labeled anomalous by the autoencoder.",
        "• The reconstruction idea is intuitive: if the network learned the baseline well, unusual rows reconstruct poorly and therefore produce larger error.",
        "",
        "7. Hybrid Anomaly Score:",
        "FLOWCHART: Isolation Forest Score + Autoencoder Score -> Weighted Blend -> Hybrid Anomaly Score -> Threshold -> Anomaly Label",
        "The AnomalyAgent combines the two model signals into a single hybrid score:",
        "hybrid_score = 0.55 * iforest_score + 0.45 * autoencoder_score",
        "The default anomaly threshold is 0.68.",
        "If hybrid_score >= 0.68 then anomaly_label = 1, else anomaly_label = 0.",
        "This weighted blending makes the final anomaly score sensitive both to isolation-based outlier structure and reconstruction-based deviation from learned normal patterns.",
        "",
        "8. Z-score Layer:",
        "A lightweight statistical anomaly layer is also computed over revenue, expenses, and cash_flow.",
        "For each column:",
        "z = (x - mean) / std",
        "The maximum absolute z-score across the selected columns is kept as the row zscore.",
        "If max_abs_zscore >= 2.5 then zscore_anomaly = 1.",
        "This layer is not the main model, but it acts as a simple secondary statistical signal.",
        "",
        "9. Payment-status Business Rules:",
        "The system contains a business override layer for invoice payment behavior.",
        "If payment_status == PARTIALLY_PAID, anomaly_score is clipped upward to at least 0.78 and risk is pushed upward.",
        "If payment_status == UNPAID, anomaly_score is clipped upward to at least 0.90 and risk is pushed to high severity.",
        "These records are treated as business anomalies even if the ML layer alone might not have marked them strongly enough.",
        "Conversely, a healthy paid small-scale profitable record can be damped if it is clearly benign and only looks unusual because it is much smaller than the enterprise baseline.",
        "",
        "10. Benign Small-scale Dampening:",
        "A protective business-sanity rule reduces false alerts for small manual records that are paid, profitable, low-risk, and have no receivable pressure.",
        "The current rule checks conditions including positive profit, low expense ratio, strong profit margin, zero receivables, non-problematic payment status, and no strong z-score anomaly.",
        "For such rows, anomaly_score is clipped down to at most 0.34, anomaly_label is cleared, risk_score is clipped to a low value, and risk_level becomes LOW.",
        "This is intentionally a hybrid design: ML first, then business logic correction.",
        "",
        "11. RiskAgent Formula:",
        "RiskAgent transforms anomaly output into a risk score using baseline comparison.",
        "It computes the training median of revenue_growth and profit_margin from the benchmark data.",
        "For each row:",
        "anomaly_component = anomaly_score * 0.55",
        "growth_penalty = 0.20 if revenue_growth < baseline_median_growth else 0.05",
        "margin_penalty = 0.20 if profit_margin < baseline_median_margin else 0.05",
        "expense_penalty = min(expense_ratio, 1.0) * 0.15",
        "risk_score = min(anomaly_component + growth_penalty + margin_penalty + expense_penalty, 1.0)",
        "Risk level thresholds are:",
        "HIGH if risk_score >= 0.75",
        "MEDIUM if risk_score >= 0.45",
        "LOW otherwise",
        "",
        "12. Bayesian Risk Scoring:",
        "The Bayesian module computes a lightweight posterior probability of risk.",
        "Inputs: anomaly_score, forecast_risk, historical_anomaly_frequency",
        "prior_risk = clamp(historical_anomaly_frequency, 0.01, 0.99)",
        "likelihood = clamp(0.55 * anomaly_score + 0.45 * forecast_risk, 0.01, 0.99)",
        "evidence = likelihood * prior_risk + (1 - likelihood) * (1 - prior_risk)",
        "posterior = (likelihood * prior_risk) / evidence",
        "risk_probability = clamp(posterior, 0, 1)",
        "uncertainty is then derived from distance to 0.5, with lower certainty near the middle and higher certainty near the extremes.",
        "This is a pragmatic Bayesian-style estimator, not a full probabilistic graphical model.",
        "",
        "13. Consensus Agent:",
        "FLOWCHART: Anomaly Score + Risk Probability + Forecast Risk + Stress Risk + Historical Frequency -> Weighted Aggregation -> Final Score + Consensus Confidence",
        "The multi-agent consensus layer aggregates several score families using configurable weights.",
        "Default weights are:",
        "anomaly_score 0.35",
        "risk_probability 0.30",
        "forecast_risk 0.15",
        "stress_risk 0.10",
        "historical_anomaly_frequency 0.10",
        "final_score = sum(weight_i * score_i)",
        "Consensus confidence is derived from dispersion: if the weighted signals disagree more, consensus confidence falls.",
        "In effect, this produces a single blended severity signal and a measure of inter-signal agreement.",
        "",
        "14. Forecasting Logic:",
        "The ForecastAgent uses Prophet to forecast revenue and expenses separately.",
        "If enough non-null history exists, Prophet is fitted with yearly seasonality enabled and weekly/daily seasonality disabled.",
        "If too little data exists or Prophet errors out, the code falls back to a carry-forward forecast that repeats the latest known value and attaches +-5 percent bounds.",
        "The forecast risk signal currently derives from recent revenue decline and expense growth in the recent engineered history.",
        "",
        "15. Stress Testing Logic:",
        "Stress testing simulates revenue drops and expense increases against the latest record.",
        "stressed_revenue = revenue * (1 - revenue_drop_pct)",
        "stressed_expenses = expenses * (1 + expense_increase_pct)",
        "stressed_profit = stressed_revenue - stressed_expenses",
        "profit_impact = stressed_profit - baseline_profit",
        "The stress risk score is a weighted combination of revenue pressure, expense pressure, and downside pressure:",
        "risk_score = 0.4 * revenue_pressure + 0.3 * expense_pressure + 0.3 * downside_pressure",
        "The platform includes 12 built-in scenarios plus a generated custom scenario ladder.",
        "",
        "16. Counterfactual Logic:",
        "Counterfactual analysis compares actual row profit against expected baseline profit.",
        "Expected profit is taken as the median profit of the last up to 6 comparable baseline rows.",
        "financial_impact = actual_profit - expected_profit",
        "A negative value indicates a loss relative to expectation; a positive value indicates a gain.",
        "",
        "17. Decision Engine:",
        "FLOWCHART: Hybrid Score -> Bayesian Risk -> Stress & Forecast Inputs -> Decision Engine -> Policy Engine -> Final Action",
        "The DecisionIntelligenceEngine combines multiple signals into a final risk estimate.",
        "final_risk = 0.25 * anomaly_score + 0.30 * risk_probability + 0.15 * forecast_risk + 0.15 * stress_risk + 0.15 * historical_anomaly_frequency",
        "confidence = clamp(0.7 * final_risk + 0.3 * consensus_confidence, 0, 1)",
        "Decision thresholds are:",
        "ALERT if final_risk >= 0.72 or financial_impact <= -20000",
        "INVESTIGATE if final_risk >= 0.45",
        "IGNORE otherwise",
        "The engine also produces severity and recommended action text.",
        "",
        "18. Policy Engine:",
        "The policy engine is a rule-based governance overlay that can override or escalate ML output.",
        "It checks high posterior risk, weak health score, high liquidity risk, large total exposure, and negative budget profit variance.",
        "If policy flags exist and the ML decision was IGNORE, the decision is raised to INVESTIGATE.",
        "If three or more policy flags exist and the decision is not already ALERT, the policy engine escalates to ALERT.",
        "Approvals are required for ALERT decisions or very high exposure states.",
        "",
        "19. Workflow Engine:",
        "Workflow orchestration is event-driven.",
        "For ALERT or INVESTIGATE decisions, a task is opened automatically.",
        "If approval is required, the system creates approval steps. For CRITICAL severity it creates Finance Manager and CFO approval stages; otherwise Finance Manager only.",
        "This makes the platform more than a score viewer: it turns model output into operational follow-up.",
        "",
        "20. Explainability and SHAP:",
        "FLOWCHART: Scored Row -> Background Sample -> KernelExplainer -> SHAP Values -> Top Features -> Explanation Text",
        "The ExplanationAgent has two modes.",
        "Quick mode sorts absolute feature magnitudes and returns the top three as a heuristic explanation.",
        "SHAP mode uses KernelExplainer on the anomaly score function, using a small background slice of the training data.",
        "The top features are selected by sorting the absolute SHAP values and returning the top three.",
        "This means the system can produce both fast approximate reasoning and more principled contribution-based reasoning when SHAP is available.",
        "",
        "21. Revenue Compare Logic:",
        "Revenue Compare does not only show one current row; it builds a comparison dataframe from merged historical sources and lets the user compare two windows.",
        "The UI aggregates the chosen metric across each window and computes a status shift such as Improved, Declined, or Flat based on the revenue delta.",
        "",
        "22. Dashboard Summary Logic:",
        "The dashboard now separates active uploaded-batch interpretation from all-time historical interpretation.",
        "The top KPI strip continues to show the latest row and its delta versus the immediately previous row in the active dataframe.",
        "The Executive Summary section uses the active dataset when an uploaded batch is being analyzed, so the user sees the current shared input rather than a confusing historical aggregate.",
        "The All-Time Performance section separately uses the historical comparison dataframe, which merges the expanded training data, baseline training data, default dataset, and current active input.",
        "This means the dashboard intentionally exposes two views at once: current operating slice and lifetime historical picture.",
        "The all-time section computes:",
        "all_time_revenue = sum(comparison_dataframe.revenue)",
        "all_time_expenses = sum(comparison_dataframe.expenses)",
        "all_time_profit = sum(comparison_dataframe.profit)",
        "all_time_profit_margin = all_time_profit / all_time_revenue",
        "all_time_anomalies = count(anomaly_label == 1)",
        "It also builds cumulative revenue, cumulative expenses, and cumulative profit via cumulative sums for historical trajectory visualization.",
        "",
        "23. Financial Operating System Analytics:",
        "Cash Flow Intelligence estimates average inflow, average outflow, net cash flow, runway, and liquidity risk.",
        "Budget vs Actual compares the latest row with a trailing median baseline.",
        "Cost Optimization estimates savings from elevated expense ratio and discretionary overspend indicators.",
        "Financial Health Score blends margin, liquidity, stability, anomaly resilience, and risk buffer into a bounded 0 to 100 score.",
        "Risk Exposure estimates operational, revenue, and cost exposure in currency terms.",
        "Loan and Credit Intelligence derives EMI capacity, estimated credit score, default risk, and optimal loan limit from cash flow and risk probability.",
        "",
        "24. XIRR Module:",
        "The XIRR implementation is written from scratch.",
        "It first tries Newton-Raphson iteration using xNPV and its derivative.",
        "If Newton-Raphson becomes unstable or fails to converge, it falls back to a bracketing and bisection search between -0.9999 and 10.0.",
        "The XIRR path is actively used by the chatbot. When the user asks about XIRR or IRR, the Chat Agent calls the local analytics.xirr.xirr function on irregular cash-flow inputs and returns the computed percentage.",
        "This makes the irregular cash-flow return calculation numerically robust enough for local use without external finance APIs.",
        "",
        "25. Chatbot Logic:",
        "The chatbot uses rule-based NLP classification rather than an external LLM API.",
        "It identifies intents such as decision questions, risk questions, invoice-status questions, capability questions, summaries, and general finance questions.",
        "Responses are grounded in the live context object returned by MonitoringService, so answers reflect the current dashboard state rather than static canned text.",
        "",
        "26. Security and RBAC Logic:",
        "The access-control layer maps roles to permissions. Admin has the broadest access, while viewer remains restricted to monitoring-focused actions.",
        "New users require approval before first access.",
        "Login attempts are tracked, repeated failures can lock the account temporarily, and alerts/tasks/approvals are logged for traceability.",
        "",
        "27. Persistence Model:",
        "SQLite is the system-of-record for local application behavior: users, anomalies, decisions, tasks, approvals, memory feedback, logs, and shared state.",
        "MySQL mirrors ingested financial data and log-style events for external inspection and reporting.",
        "The logs mirror includes navigation, uploads, downloads, logout, chat interactions, login attempts, and error conditions.",
        "",
        "28. Performance Design:",
        "Training artifacts are cached. The scaler, fitted Isolation Forest, and fitted autoencoder are reused unless the training-data token changes.",
        "This prevents expensive retraining on every UI rerun and keeps interaction latency low enough for dashboard use.",
        "• This cache design is critical in Streamlit because reruns happen frequently and would otherwise retrain models unnecessarily.",
        "",
        "29. Current Context Snapshot:",
        f"Latest decision: {latest_decision.get('decision', 'N/A')}",
        f"Latest confidence score: {latest_decision.get('confidence_score', 0.0):.2f}",
        f"Latest risk probability: {latest_decision.get('risk_probability', 0.0):.2f}",
        f"Latest consensus confidence: {latest_decision.get('consensus_confidence', 0.0):.2f}",
        f"Latest financial impact: {latest_decision.get('financial_impact', 0.0):,.0f}",
        f"Email alerts enabled: {email_enabled}",
        "",
        "30. Interpretation Guidance:",
        "No single score should be read in isolation.",
        "The anomaly score says how unusual the row is.",
        "The Bayesian risk probability says how risky it likely is after folding in prior frequency and forecast context.",
        "The decision engine says what to do operationally.",
        "The policy engine says whether governance rules demand escalation beyond what the model alone would do.",
        "The explainability layer says why the model reacted the way it did.",
        "",
        "31. Practical Summary:",
        "The software is intentionally hybrid. It is not pure ML and it is not pure business rules.",
        "The design is: preprocess -> model score -> statistical checks -> business-rule adjustment -> risk estimation -> decision -> policy review -> workflow action -> explanation -> persistence -> UI/chat delivery.",
        "That layered design is the core logic of the system.",
        "• The best way to read the platform is as a decision intelligence stack rather than a single anomaly model.",
    ]


def _build_visual_guide_svg(title: str, subtitle: str, chips: list[str], footer: str, accent: str = "#14b8a6") -> bytes:
    """Create a polished screenshot-style SVG for the manual visual guide."""
    safe_title = html_escape(title)
    safe_subtitle = html_escape(subtitle)
    safe_footer = html_escape(footer)
    chip_markup: list[str] = []
    chip_x = 78
    for chip in chips[:4]:
        safe_chip = html_escape(chip)
        width = max(136, min(250, 18 + (len(chip) * 9)))
        chip_markup.append(
            f'<rect x="{chip_x}" y="192" width="{width}" height="34" rx="17" fill="#eaf6ff" stroke="#b8dfff"/>'
            f'<text x="{chip_x + 18}" y="214" font-size="16" font-family="Segoe UI, Arial" font-weight="600" fill="#0b4d78">{safe_chip}</text>'
        )
        chip_x += width + 16

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="860" viewBox="0 0 1400 860">
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="#fff8ef"/>
      <stop offset="100%" stop-color="#eef6ff"/>
    </linearGradient>
    <linearGradient id="hero" x1="0" x2="1">
      <stop offset="0%" stop-color="#10213c"/>
      <stop offset="50%" stop-color="#2155d6"/>
      <stop offset="100%" stop-color="{accent}"/>
    </linearGradient>
  </defs>
  <rect width="1400" height="860" fill="url(#bg)"/>
  <rect x="46" y="46" width="1308" height="122" rx="28" fill="url(#hero)"/>
  <text x="82" y="102" font-size="42" font-family="Segoe UI, Arial" font-weight="700" fill="#fff8ef">{safe_title}</text>
  <text x="82" y="140" font-size="20" font-family="Segoe UI, Arial" fill="#e7eef9">{safe_subtitle}</text>
  {"".join(chip_markup)}
  <rect x="76" y="255" width="392" height="214" rx="24" fill="#ffffff" stroke="#cae7ff"/>
  <rect x="504" y="255" width="392" height="214" rx="24" fill="#ffffff" stroke="#cae7ff"/>
  <rect x="932" y="255" width="392" height="214" rx="24" fill="#ffffff" stroke="#cae7ff"/>
  <text x="108" y="313" font-size="24" font-family="Segoe UI, Arial" fill="#27415d">Executive Signal</text>
  <text x="108" y="384" font-size="56" font-family="Segoe UI, Arial" fill="#10213c">0.78</text>
  <text x="108" y="426" font-size="18" font-family="Segoe UI, Arial" fill="#0f9f6e">Aligned with live decision context</text>
  <text x="536" y="313" font-size="24" font-family="Segoe UI, Arial" fill="#27415d">Business Pulse</text>
  <text x="536" y="384" font-size="56" font-family="Segoe UI, Arial" fill="#10213c">Stable</text>
  <text x="536" y="426" font-size="18" font-family="Segoe UI, Arial" fill="#0f9f6e">Context-aware summary block</text>
  <text x="965" y="313" font-size="24" font-family="Segoe UI, Arial" fill="#27415d">Operator Action</text>
  <text x="965" y="384" font-size="56" font-family="Segoe UI, Arial" fill="#10213c">Review</text>
  <text x="965" y="426" font-size="18" font-family="Segoe UI, Arial" fill="#d25d2e">Escalation path and guidance</text>
  <rect x="76" y="508" width="598" height="274" rx="24" fill="#ffffff" stroke="#cae7ff"/>
  <rect x="726" y="508" width="598" height="274" rx="24" fill="#ffffff" stroke="#cae7ff"/>
  <text x="108" y="564" font-size="30" font-family="Segoe UI, Arial" font-weight="700" fill="#162338">Visual Focus</text>
  <polyline points="118,734 198,704 278,654 358,676 438,606 518,626 618,574" fill="none" stroke="#2155d6" stroke-width="7" stroke-linecap="round"/>
  <circle cx="118" cy="734" r="7" fill="#2155d6"/><circle cx="198" cy="704" r="7" fill="#2155d6"/><circle cx="278" cy="654" r="7" fill="#2155d6"/><circle cx="358" cy="676" r="7" fill="#2155d6"/><circle cx="438" cy="606" r="7" fill="#2155d6"/><circle cx="518" cy="626" r="7" fill="#2155d6"/><circle cx="618" cy="574" r="7" fill="#2155d6"/>
  <text x="758" y="564" font-size="30" font-family="Segoe UI, Arial" font-weight="700" fill="#162338">Usage Notes</text>
  <rect x="760" y="602" width="524" height="38" rx="12" fill="#f8fbff" stroke="#d8ebfb"/>
  <rect x="760" y="654" width="524" height="38" rx="12" fill="#f8fbff" stroke="#d8ebfb"/>
  <rect x="760" y="706" width="524" height="38" rx="12" fill="#f8fbff" stroke="#d8ebfb"/>
  <text x="782" y="627" font-size="18" font-family="Segoe UI, Arial" fill="#203247">Live metrics, charts, and decisions stay aligned.</text>
  <text x="782" y="679" font-size="18" font-family="Segoe UI, Arial" fill="#203247">Guide text appears directly below each visual in-app.</text>
  <text x="782" y="731" font-size="18" font-family="Segoe UI, Arial" fill="#203247">{safe_footer}</text>
</svg>
"""
    return svg.encode("utf-8")


def _render_visual_guide_card(title: str, subtitle: str, description: str, chips: list[str], footer: str, accent: str) -> None:
    """Render one visual guide card with text directly below the image."""
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.image(_build_visual_guide_svg(title, subtitle, chips, footer, accent=accent), width="stretch")
    st.markdown(f"#### {title}")
    st.write(description)
    st.caption(footer)
    st.markdown("</div>", unsafe_allow_html=True)


def render_manual_tab(context: dict) -> None:
    """Render a detailed built-in software manual with terminology, SHAP notes, visuals, and PDF export."""
    assets_dir = PROJECT_ROOT / "assets"
    dashboard_preview = assets_dir / "manual_dashboard.svg"
    command_deck_preview = assets_dir / "manual_command_deck.svg"
    input_preview = assets_dir / "manual_input_studio.svg"
    username = st.session_state.get("authenticated_user", "user")
    is_admin = context.get("user_profile", {}).get("role", "viewer") == "admin"
    manual_lines = build_manual_lines(context, username)
    manual_pdf = REPORTING_SERVICE.build_manual_pdf(
        manual_lines,
        title="Financial Operating System Manual",
        subtitle="User-facing guide with features, terminology, workflow notes, SHAP overview, and visual walkthroughs.",
        watermark_text="Financial OS Manual",
    )
    technical_manual_lines = build_technical_manual_lines(context, username)
    technical_manual_pdf = REPORTING_SERVICE.build_manual_pdf(
        technical_manual_lines,
        title="Financial Operating System Technical Logic Manual",
        subtitle="In-depth explanation of algorithms, formulas, orchestration logic, thresholds, storage, and model behavior.",
        watermark_text="Technical Logic Manual",
        technical=True,
    )

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Manual & Instructions")
    st.write(
        "This workspace is a financial operating system that monitors incoming data, detects anomalies, scores risk, forecasts trends, runs scenarios, logs decisions, and explains findings through a chatbot."
    )
    download_col1, download_col2 = st.columns(2)
    manual_download = download_col1.download_button(
        "Download User Manual PDF",
        data=manual_pdf,
        file_name="financial_operating_system_manual.pdf",
        mime="application/pdf",
        width="stretch",
    )
    technical_download = download_col2.download_button(
        "Download Technical Logic PDF",
        data=technical_manual_pdf,
        file_name="financial_operating_system_technical_logic.pdf",
        mime="application/pdf",
        disabled=not is_admin,
        width="stretch",
    )
    if manual_download:
        log_event(username, "download_manual_pdf", {"lines": len(manual_lines)})
    if technical_download:
        log_event(username, "download_technical_manual_pdf", {"lines": len(technical_manual_lines)})
    if not is_admin:
        st.caption("The technical logic PDF is restricted to admin accounts. The user manual remains available to all roles.")
    st.markdown("</div>", unsafe_allow_html=True)

    overview_tab, terminology_tab, explainability_tab, workflow_tab, visual_tab = st.tabs(
        ["Overview", "Terminology", "Explainability & SHAP", "Workflow", "Visual Guide"]
    )

    with overview_tab:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### What This Software Does")
        st.write("It ingests financial records from the default dataset, uploaded files, unstructured invoice text, and manual entry.")
        st.write("It compares each record against the training baseline and combines anomaly detection, risk scoring, policy rules, forecasting, consensus logic, and workflow automation.")
        st.write("It stores alerts, decisions, chat activity, exports, and shared submissions in SQLite and mirrors key data into MySQL.")
        st.markdown("### Quick Start")
        st.write("1. Sign in with an approved account.")
        st.write("2. Open the dashboard to review KPIs, alerts, and trends.")
        st.write("3. Use the Data Input Studio for structured, unstructured, or manual ingestion.")
        st.write("4. Review anomalies in Decision Intelligence and acknowledge any active alerts.")
        st.write("5. Use Chat Assistant for explanations, summaries, and follow-up questions.")
        st.write("6. Use Command Brief or this manual tab when you need downloadable documentation.")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### Tab Guide")
        tab_rows = pd.DataFrame(
            [
                {"Tab": "Overview", "Purpose": "Executive KPIs, anomaly trend, financial trend, forecast, and profit-bridge views."},
                {"Tab": "Revenue Compare", "Purpose": "Compare two date intervals for revenue, expenses, profit, and anomaly level."},
                {"Tab": "Decision Intelligence", "Purpose": "Shows latest decision, reasoning trace, risk probability, consensus, and recommended action."},
                {"Tab": "Operating System", "Purpose": "Operating-finance modules such as cash flow intelligence, budget vs actual, health score, exposure, and optimization."},
                {"Tab": "Governance", "Purpose": "Tasks, approvals, agent outputs, and audit-oriented operating workflow information."},
                {"Tab": "Access & Security", "Purpose": "Admin-only management for roles, account state, approvals, and security activity."},
                {"Tab": "Explainability", "Purpose": "Feature-level anomaly interpretation and SHAP-supported reasoning when available."},
                {"Tab": "Scenario Lab", "Purpose": "Run built-in and generated stress scenarios to test profit and risk impact."},
                {"Tab": "Chat Assistant", "Purpose": "Ask finance questions in natural language and receive live context-aware answers."},
                {"Tab": "Command Brief", "Purpose": "Download the current state as PDF or CSV reports."},
                {"Tab": "Manual & Instructions", "Purpose": "Deep product guide with terminology, screenshots, explainability notes, and workflow instructions."},
            ]
        )
        st.dataframe(tab_rows, width="stretch", hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with terminology_tab:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### Terminology")
        glossary_items = [
            ("Revenue", "The incoming business value captured from invoices or transactions."),
            ("Expenses", "The cost attributed to generating or delivering that revenue."),
            ("Profit", "Revenue minus expenses."),
            ("Profit Margin", "Profit divided by revenue. Higher values usually indicate healthier efficiency."),
            ("Expense Ratio", "Expenses divided by revenue. Higher values may indicate pressure on margins."),
            ("Anomaly Score", "A 0 to 1 score estimating how unusual a record looks compared with trained history."),
            ("Risk Probability", "The Bayesian probability that the record should be treated as risky."),
            ("Decision", "The system action chosen from ALERT, INVESTIGATE, or IGNORE."),
            ("Consensus Confidence", "How strongly the multi-agent signals agree with each other."),
            ("Counterfactual Impact", "The difference between expected financial outcome and actual outcome."),
            ("Risk Exposure", "The estimated monetary exposure implied by current signals and business dependencies."),
            ("Financial Health Score", "A composite score that summarizes the current health of the operating environment."),
        ]
        for term, meaning in glossary_items:
            st.write(f"**{term}**: {meaning}")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### Chart Guide")
        chart_items = [
            ("Anomaly Timeline", "Shows anomaly score over time so spikes stand out quickly."),
            ("Financial Trends", "Plots revenue, expenses, and profit together to reveal movement and gaps."),
            ("Forecast Outlook", "Extends future revenue and expense expectations using Prophet."),
            ("Revenue to Profit Bridge", "Waterfall-style breakdown from revenue through expenses to retained outcome."),
            ("Profit Margin Trend", "Shows how profitability efficiency changes across time."),
            ("Impact Visualization", "Maps how one metric affects downstream financial metrics."),
        ]
        for term, meaning in chart_items:
            st.write(f"**{term}**: {meaning}")
        st.markdown("### Alert Meanings")
        st.write("**ALERT** means the system believes a record needs immediate attention.")
        st.write("**INVESTIGATE** means the record looks notable and should be reviewed.")
        st.write("**IGNORE** means the record is acceptable after model and policy review.")
        st.markdown("</div>", unsafe_allow_html=True)

    with explainability_tab:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### Explainability Engine")
        st.write("The Explainability tab answers one core question: why did the system think this record was unusual?")
        st.write("The Explanation Agent supports both a fast heuristic path and a SHAP path.")
        st.write("When SHAP is available, the system estimates each feature's contribution to the anomaly output and ranks the top drivers.")
        st.write("When SHAP is unavailable, the app falls back to a fast heuristic explanation so the dashboard remains stable and responsive.")
        st.markdown("### SHAP in Plain Words")
        st.write("A larger SHAP impact means that feature pushed the record more strongly toward anomalous behavior.")
        st.write("For example, if `expense_ratio` is high and appears as a top driver, the model is reading that record as expensive relative to revenue.")
        st.write("If `profit_margin` is unusually high or low compared with the baseline, SHAP can surface that too.")
        st.write("If `accounts_receivable` is elevated, SHAP may indicate that collection risk contributed to the anomaly score.")
        st.write("SHAP is an explanation layer. It helps users interpret model behavior; it does not replace the final decision and policy logic.")
        st.markdown("</div>", unsafe_allow_html=True)

    with workflow_tab:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### Input Modes")
        st.write("**Structured File** accepts CSV, JSON, and TXT datasets with financial columns.")
        st.write("**Unstructured Text** reads invoice-style free text or text-based PDFs and extracts invoice IDs, dates, totals, paid amount, receivables, and status.")
        st.write("**Manual Entry** is locked to today's date, auto-generates transaction IDs, and increments them from the latest manual record.")
        st.write("Manual submissions and uploads are validated before they become the shared dashboard dataset.")
        st.markdown("### Security and Roles")
        st.write("Admins have full access, including logs, approvals, governance, and security controls.")
        st.write("Viewers can monitor the dashboard but cannot change shared data.")
        st.write("New users stay pending until an admin approves them.")
        st.markdown("### Data Storage")
        st.write("SQLite stores application state locally, while MySQL mirrors logs and ingested financial data for external viewing.")
        st.write("Training baseline rows and future shared submissions are stored in MySQL under `financial_monitor.ingested_financial_data`.")
        st.write("Application actions such as navigation, uploads, chat events, downloads, and login attempts are mirrored into MySQL logs.")
        st.markdown("</div>", unsafe_allow_html=True)

    with visual_tab:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### Visual Walkthrough")
        st.write("This gallery explains the software screen by screen. Each image is paired with a short explanation directly underneath so a new user can understand what to look at, why it matters, and how each screen connects to the decision pipeline.")
        st.write("The guide covers the executive dashboard, compare tools, decision layers, governance surfaces, explainability, scenarios, chat, reporting, and every data-entry mode.")
        st.markdown("</div>", unsafe_allow_html=True)

        guide_items = [
            {
                "title": "01. Dashboard Hero",
                "subtitle": "Header, status ribbon, role ribbon, and current shared source.",
                "description": "Use this screen first to confirm who is logged in, which tenant is active, and whether the dashboard is showing the default dataset or a live shared submission. It is the orientation layer for the rest of the product.",
                "chips": ["Status Ribbon", "Role", "Tenant", "Live Source"],
                "footer": "Read this header before interpreting downstream KPIs so you know exactly which dataset is in view.",
                "accent": "#14b8a6",
            },
            {
                "title": "02. Command Deck",
                "subtitle": "Navigation, refresh, logout, and alert administration.",
                "description": "The Command Deck is the left-side control surface. It keeps navigation and actions consistent, so users can move between dashboard views, logs, and account actions without losing orientation.",
                "chips": ["Navigation", "Actions", "Alerts", "Security"],
                "footer": "Think of the Command Deck as the operations sidebar that controls movement, refresh, and alert settings.",
                "accent": "#0ea5e9",
            },
            {
                "title": "03. Executive Summary",
                "subtitle": "Totals for revenue, expenses, profit, losses, margin, and anomaly count.",
                "description": "This section summarizes the current operating picture. It separates the latest row KPIs from broader totals so users can understand both the most recent observation and the larger business state.",
                "chips": ["Totals", "Profit", "Losses", "Margin"],
                "footer": "Use this section when leadership wants the highest-level financial picture without opening deeper diagnostics.",
                "accent": "#22c55e",
            },
            {
                "title": "04. All-Time Performance",
                "subtitle": "Lifetime revenue, expenses, profit margin, and anomaly volume.",
                "description": "This screen is designed for longitudinal reading. It pulls from the historical comparison dataframe so users can see business performance across the full retained timeline, not just the latest upload.",
                "chips": ["All-Time", "Cumulative", "Anomalies", "History"],
                "footer": "This is the best screen for understanding long-run scale, historical efficiency, and accumulated anomaly pressure.",
                "accent": "#f59e0b",
            },
            {
                "title": "05. Anomaly Timeline",
                "subtitle": "Time-ordered anomaly score movement and spike detection.",
                "description": "The anomaly timeline is used for pattern reading. Spikes, clusters, and repeated oscillations help users distinguish one-off anomalies from persistent operational drift.",
                "chips": ["Spikes", "Clusters", "Trend", "Timing"],
                "footer": "Look for sudden breaks, repeated bursts, or long elevated bands rather than only isolated points.",
                "accent": "#ef4444",
            },
            {
                "title": "06. Revenue Compare",
                "subtitle": "Two-window comparison for revenue, expenses, profit, and anomaly average.",
                "description": "This compare tool is for business questions like 'How does this month compare with January?' or 'What changed between the last two operating periods?' It turns date windows into a direct side-by-side operational comparison.",
                "chips": ["Window A", "Window B", "Compare", "Variance"],
                "footer": "Use this tab for period-over-period analysis instead of visually estimating differences from the main line charts.",
                "accent": "#8b5cf6",
            },
            {
                "title": "07. Decision Intelligence",
                "subtitle": "Decision, confidence, Bayesian risk, recommendation, and reasoning trace.",
                "description": "This screen explains what the system wants the operator to do. It combines anomaly evidence, Bayesian risk, stress signals, consensus, and policy review into a clear operational action.",
                "chips": ["Decision", "Confidence", "Risk", "Trace"],
                "footer": "Read this tab when you need both the action and the explanation for why that action was selected.",
                "accent": "#06b6d4",
            },
            {
                "title": "08. Explainability and SHAP",
                "subtitle": "Top feature drivers behind the anomaly score.",
                "description": "The explainability screen answers why the model reacted. When SHAP is available, the tab surfaces feature-level contributions; otherwise the app falls back to heuristic rankings so the workflow still remains useful.",
                "chips": ["SHAP", "Drivers", "Feature Impact", "Fallback"],
                "footer": "This tab is the bridge between opaque model behavior and a human-readable diagnostic story.",
                "accent": "#ec4899",
            },
            {
                "title": "09. Operating System",
                "subtitle": "Cash flow intelligence, budget variance, exposure, optimization, and health score.",
                "description": "This area extends beyond anomaly detection into financial operations management. It summarizes liquidity, efficiency, exposure, and optimization opportunities so the platform feels like an operating system instead of a narrow detector.",
                "chips": ["Liquidity", "Exposure", "Optimization", "Health"],
                "footer": "Use this tab when the question is broader than a single anomaly and includes runway, operating quality, or savings opportunities.",
                "accent": "#10b981",
            },
            {
                "title": "10. Governance",
                "subtitle": "Tasks, approvals, agent outputs, and traceability records.",
                "description": "Governance turns findings into accountable workflow. This screen is where approvals, follow-up tasks, and multi-agent outputs become part of the audit trail.",
                "chips": ["Approvals", "Tasks", "Audit", "Traceability"],
                "footer": "This is the tab to open when a decision must be reviewed, tracked, or formally approved.",
                "accent": "#f97316",
            },
            {
                "title": "11. Access and Security",
                "subtitle": "Roles, account state, approval queue, and security control panel.",
                "description": "This screen is designed for administrators. It governs who can access what, which users are pending, how accounts are managed, and how operational security remains controlled over time.",
                "chips": ["Roles", "Accounts", "Approvals", "Security"],
                "footer": "Use this section to manage permissions without weakening the audit trail or bypassing the approval model.",
                "accent": "#0f766e",
            },
            {
                "title": "12. Scenario Lab",
                "subtitle": "Stress testing, scenario generation, and downstream impact simulation.",
                "description": "The Scenario Lab lets users test what-if conditions such as revenue drops, cost increases, and more complex stress cases. It is the best place to ask how the system would behave under alternative business conditions.",
                "chips": ["Stress Test", "Custom", "Impact", "Forecast"],
                "footer": "This screen is for proactive planning rather than retrospective monitoring.",
                "accent": "#7c3aed",
            },
            {
                "title": "13. Chat Assistant",
                "subtitle": "Natural-language Q&A grounded in the live system context.",
                "description": "The chatbot is connected to the current dashboard context, not a detached FAQ. It can answer about anomalies, decisions, forecasts, roles, invoice state, logs, and XIRR using the live data assembled by the service layer.",
                "chips": ["Context", "NLP", "Chat", "XIRR"],
                "footer": "Use the chat interface when you want the platform to summarize, explain, or retrieve a specific answer quickly.",
                "accent": "#2563eb",
            },
            {
                "title": "14. Command Brief",
                "subtitle": "Downloadable PDF and CSV reports for stakeholders.",
                "description": "This tab packages the current state into formal output. It is designed for sharing the current operating picture with decision-makers without asking them to interpret the full dashboard manually.",
                "chips": ["PDF", "CSV", "Reports", "Share"],
                "footer": "Use this when leadership needs a clean export instead of a live app walkthrough.",
                "accent": "#0891b2",
            },
            {
                "title": "15. Structured Input",
                "subtitle": "Upload well-formed CSV, JSON, or TXT financial tables.",
                "description": "This repository screen handles structured datasets. It validates required columns, sanitizes values, preserves payment status as categorical text, and sends the cleaned batch into the same analysis pipeline as the baseline data.",
                "chips": ["CSV", "JSON", "Validation", "Columns"],
                "footer": "Use this mode when finance data already exists in rows and columns.",
                "accent": "#16a34a",
            },
            {
                "title": "16. Unstructured, Manual, and Alert Flow",
                "subtitle": "Invoice extraction, locked manual entry, and acknowledgement behavior.",
                "description": "Unstructured input parses invoice-like text and text-based PDFs, manual entry generates locked transaction IDs and today-only records, and active anomalies remain visible until the user explicitly acknowledges them. Together these screens show how the product handles messy inputs, direct user entry, and persistent operator attention.",
                "chips": ["PDF", "Manual Entry", "Alerts", "Acknowledge"],
                "footer": "This combined flow explains how the platform converts raw business documents and operator actions into governed dashboard state.",
                "accent": "#dc2626",
            },
        ]

        for start in range(0, len(guide_items), 3):
            columns = st.columns(3)
            for column, item in zip(columns, guide_items[start:start + 3]):
                with column:
                    _render_visual_guide_card(
                        item["title"],
                        item["subtitle"],
                        item["description"],
                        item["chips"],
                        item["footer"],
                        item["accent"],
                    )


def render_chat_dock(context: dict) -> None:
    """Render a compact always-available chat dock that the floating launcher can target."""
    _ensure_chat_state()
    st.markdown('<div id="copilot-dock"></div>', unsafe_allow_html=True)
    st.markdown('<div class="chat-dock">', unsafe_allow_html=True)
    st.subheader("Copilot Dock")
    st.caption("Fast access PDA-style launcher for quick questions.")
    last_assistant_message = next(
        (message for speaker, message in reversed(st.session_state.chat_history) if speaker == "assistant"),
        "Ask a quick question about anomalies, risk, or actions.",
    )
    st.write(last_assistant_message)
    with st.form("chat_dock_form", clear_on_submit=True):
        dock_col1, dock_col2 = st.columns([5, 1])
        dock_prompt = dock_col1.text_input(
            "Quick Copilot Prompt",
            key="dock_prompt_input",
            label_visibility="collapsed",
            placeholder="What changed in the latest anomaly?",
        )
        send_dock_prompt = dock_col2.form_submit_button("Send")
    if send_dock_prompt and dock_prompt.strip():
        handle_chat_prompt(context, dock_prompt.strip())
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def render_floating_chat_launcher() -> None:
    """Render a floating PDA-style launcher."""
    st.markdown(
        """
        <a class="floating-chat-launcher" href="#copilot-dock" title="Open Copilot Dock">
            PDA<br>Chat
        </a>
        """,
        unsafe_allow_html=True,
    )


def render_logs_page(context: dict, username: str) -> None:
    """Render structured logs with filters and exports."""
    if not has_permission(context, "view_logs"):
        render_permission_notice("Logs", "Audit logs are restricted to reviewer and admin roles.")
        return
    database_logs = pd.DataFrame(context["database_manager"].get_logs(limit=None))
    event_logs = pd.DataFrame(read_event_logs())

    if database_logs.empty and event_logs.empty:
        st.info("No logs are available yet.")
        return

    frames = []
    if not database_logs.empty:
        database_logs = database_logs.rename(columns={"user_name": "user", "event_time": "timestamp"})
        database_logs["source"] = "database"
        frames.append(database_logs)
    if not event_logs.empty:
        event_logs["source"] = "file"
        frames.append(event_logs)

    logs_df = pd.concat(frames, ignore_index=True).fillna("")
    logs_df["timestamp"] = logs_df["timestamp"].apply(to_ist_timestamp)
    logs_df = logs_df.dropna(subset=["timestamp"]).copy()
    if logs_df.empty:
        st.info("Logs exist, but none have a valid timestamp yet.")
        return

    logs_df["timestamp_label"] = logs_df["timestamp"].apply(lambda value: value.strftime("%Y-%m-%d %H:%M:%S IST"))
    logs_df["log_date"] = logs_df["timestamp"].dt.date
    min_date = logs_df["log_date"].min()
    max_date = logs_df["log_date"].max()

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    selected_date = col1.date_input("Filter by date", value=max_date, min_value=min_date, max_value=max_date)
    action_options = ["All"] + sorted(value for value in logs_df["action"].astype(str).unique() if value)
    selected_action = col2.selectbox("Filter by action", action_options)

    filtered = logs_df[logs_df["log_date"] == selected_date].copy()
    if selected_action != "All":
        filtered = filtered[filtered["action"] == selected_action].copy()

    st.dataframe(
        filtered.sort_values("timestamp", ascending=False)[["timestamp_label", "source", "user", "action", "message"]].rename(
            columns={"timestamp_label": "timestamp"}
        ),
        width="stretch",
        height=520,
    )
    download_col1, download_col2 = st.columns(2)
    logs_pdf = REPORTING_SERVICE.build_logs_pdf(filtered.sort_values("timestamp", ascending=False))
    pdf_clicked = download_col1.download_button(
        "Download Logs PDF",
        data=logs_pdf,
        file_name=f"system_logs_{selected_date}.pdf",
        mime="application/pdf",
        disabled=not has_permission(context, "download_reports"),
    )
    csv_clicked = download_col2.download_button(
        "Download Logs CSV",
        data=filtered.drop(columns=["timestamp"]).assign(timestamp=filtered["timestamp_label"]).to_csv(index=False).encode("utf-8"),
        file_name=f"system_logs_{selected_date}.csv",
        mime="text/csv",
        disabled=not has_permission(context, "download_reports"),
    )
    if pdf_clicked:
        log_event(username, "download_logs_pdf", {"date": str(selected_date), "action": selected_action, "rows": len(filtered)})
    if csv_clicked:
        log_event(username, "download_logs_csv", {"date": str(selected_date), "action": selected_action, "rows": len(filtered)})
    if not has_permission(context, "download_reports"):
        st.caption("Log exports are restricted for your role.")
    st.markdown("</div>", unsafe_allow_html=True)


def render_dashboard(context: dict, username: str) -> None:
    """Render the dashboard tabs."""
    tab_specs = [
        ("Overview", lambda: render_overview_tab(context)),
        ("Revenue Compare", lambda: render_revenue_compare_tab(context)),
    ]
    if has_permission(context, "view_decision_intelligence"):
        tab_specs.append(("Decision Intelligence", lambda: render_intelligence_tab(context)))
    if has_permission(context, "view_operating_system"):
        tab_specs.append(("Operating System", lambda: render_operating_system_tab(context)))
    if has_permission(context, "view_governance"):
        tab_specs.append(("Governance", lambda: render_governance_tab(context)))
    if has_permission(context, "manage_users") or has_permission(context, "manage_security"):
        tab_specs.append(("Access & Security", lambda: render_access_security_tab(context, username)))
    if has_permission(context, "view_explainability"):
        tab_specs.append(("Explainability", lambda: render_explainability_tab(context)))
    if has_permission(context, "run_scenarios"):
        tab_specs.append(("Scenario Lab", lambda: render_simulation_tab(context, username)))
    if has_permission(context, "use_chat"):
        tab_specs.append(("Chat Assistant", lambda: render_chat_tab(context)))
    tab_specs.append(("Command Brief", lambda: render_command_brief_tab(context, username)))
    tab_specs.append(("Manual & Instructions", lambda: render_manual_tab(context)))

    tabs = st.tabs([label for label, _ in tab_specs])
    for tab, (_, renderer) in zip(tabs, tab_specs):
        with tab:
            renderer()
    if has_permission(context, "use_chat"):
        render_chat_dock(context)
        render_floating_chat_launcher()


def main() -> None:
    """Application entrypoint with authentication and tabbed dashboard layout."""
    apply_classic_theme()
    username = require_login(DATABASE, "dashboard")
    st.session_state["authenticated_user"] = username
    try:
        _ensure_chat_state()
        context = get_preferred_context()
        render_hero(context, username)
        render_alert_center(context, username)

        with st.sidebar:
            st.header("Command Deck")
            permissions = context.get("permissions", {})
            user_profile = context.get("user_profile", {})
            st.markdown(
                f"""
                <div class="command-card">
                    <div class="command-card-title">{user_profile.get('tenant_name', 'Default Finance')}</div>
                    <div class="command-card-subtitle">{username} | {user_profile.get('role', 'viewer').title()}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if "dashboard_page" not in st.session_state:
                st.session_state["dashboard_page"] = "Dashboard"
            st.markdown('<div class="command-section-title">Navigation</div>', unsafe_allow_html=True)
            if st.button("Dashboard", key="nav_dashboard", width="stretch"):
                st.session_state["dashboard_page"] = "Dashboard"
                log_event(username, "navigate", {"target": "Dashboard"})
                st.rerun()
            logs_disabled = not permissions.get("view_logs", False)
            if st.button("Logs", key="nav_logs", disabled=logs_disabled, width="stretch"):
                st.session_state["dashboard_page"] = "Logs"
                log_event(username, "navigate", {"target": "Logs"})
                st.rerun()
            st.markdown('<div class="command-section-title">Actions</div>', unsafe_allow_html=True)
            refresh_disabled = not permissions.get("refresh_context", False)
            if st.button("Refresh", key="nav_refresh", disabled=refresh_disabled, width="stretch"):
                log_event(username, "refresh_context", "Dashboard refreshed from shared input state")
                st.rerun()
            if st.button("Logout", key="nav_logout", width="stretch"):
                log_event(username, "logout", {"message": "User signed out"})
                logout_user("dashboard")
                st.session_state.pop("authenticated_user", None)
                st.session_state.pop("chat_history", None)
                st.rerun()
            if permissions.get("manage_alerts", False):
                st.markdown('<div class="command-section-title">Alerts</div>', unsafe_allow_html=True)
                with st.expander("Email Alert Settings"):
                    current_settings = context.get("email_alert_settings", {})
                    with st.form("email_alert_settings_form", clear_on_submit=False):
                        enabled = st.checkbox("Enable anomaly email alerts", value=current_settings.get("enabled", "").lower() == "true")
                        smtp_host = st.text_input("SMTP Host", value=current_settings.get("smtp_host", ""))
                        smtp_port = st.text_input("SMTP Port", value=current_settings.get("smtp_port", "587"))
                        smtp_username = st.text_input("SMTP Username", value=current_settings.get("smtp_username", ""))
                        smtp_password = st.text_input("SMTP Password", type="password", value=current_settings.get("smtp_password", ""))
                        from_email = st.text_input("From Email", value=current_settings.get("from_email", ""))
                        recipients = st.text_area("Recipients (comma separated)", value=current_settings.get("recipients", ""))
                        save_alert_settings = st.form_submit_button("Save Alert Settings")
                    if save_alert_settings:
                        SERVICE.save_email_alert_settings(
                            {
                                "enabled": "true" if enabled else "false",
                                "smtp_host": smtp_host,
                                "smtp_port": smtp_port,
                                "smtp_username": smtp_username,
                                "smtp_password": smtp_password,
                                "from_email": from_email,
                                "recipients": recipients,
                            }
                        )
                        log_event(username, "save_email_alert_settings", {"enabled": enabled, "recipients": recipients})
                        st.success("Email alert settings saved.")
                        st.rerun()

        if st.session_state.get("dashboard_page", "Dashboard") == "Dashboard" or not permissions.get("view_logs", False):
            render_dashboard(context, username)
        else:
            render_logs_page(context, username)
    except Exception as exc:
        log_event("system", "ui_error", {"error": str(exc)}, level="ERROR")
        st.error(f"The application hit an unexpected error: {exc}")


if __name__ == "__main__":
    main()
