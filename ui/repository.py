from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import DATABASE, SERVICE
from ui.auth_ui import require_login
from ui.theme import apply_classic_theme
from services.access_control import AccessControl
from utils.logger import log_event
from utils.preprocessing import (
    build_manual_entry_dataframe,
    extract_text_from_document,
    generate_basic_financial_insights,
    parse_unstructured_financial_text,
    parse_uploaded_file,
    validate_financial_dataframe,
)


st.set_page_config(page_title="Data Input Studio", layout="wide")
ACCESS_CONTROL = AccessControl()


def _extract_manual_transaction_sequence(value: object) -> int | None:
    """Extract the numeric suffix from a MANUAL-style transaction ID."""
    text = str(value or "").strip().upper()
    if not text.startswith("MANUAL-"):
        return None
    suffix = text.split("MANUAL-", 1)[1]
    return int(suffix) if suffix.isdigit() else None


def _get_next_manual_transaction_ids(record_count: int) -> list[str]:
    """Generate the next locked manual transaction IDs from existing data."""
    candidate_frames: list[pd.DataFrame] = []
    for path_string in [
        "data/shared_input.csv",
        "data/financial_data.csv",
        "data/training_financial_data.csv",
        "data/expanded_training_financial_data.csv",
    ]:
        path = Path(path_string)
        if not path.exists():
            continue
        try:
            candidate_frames.append(pd.read_csv(path))
        except Exception:
            continue

    max_sequence = 0
    for frame in candidate_frames:
        if "transaction_id" not in frame.columns:
            continue
        for value in frame["transaction_id"].tolist():
            sequence = _extract_manual_transaction_sequence(value)
            if sequence is not None:
                max_sequence = max(max_sequence, sequence)

    start_value = max_sequence + 1
    return [f"MANUAL-{index:03d}" for index in range(start_value, start_value + int(record_count))]


def render_header(username: str) -> None:
    """Render the dedicated data input page header."""
    st.markdown(
        f"""
        <div class="hero-card">
            <div class="hero-title">Data Input Studio</div>
            <div class="hero-subtitle">
                Logged in as {username}. Submit structured files, paste unstructured finance notes, or enter records manually.
                Every successful submission is saved and reflected in the dashboard automatically.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def analyze_and_share_dataframe(df: pd.DataFrame, source_label: str, username: str) -> None:
    """Validate, analyze, and publish a dataset to the dashboard."""
    today = date.today()
    normalized_dates = pd.to_datetime(df["date"], errors="coerce").dt.date
    if normalized_dates.isna().any():
        st.error("Every submitted record must have a valid date.")
        log_event(username, "input_validation_failed", {"source": source_label, "message": "Invalid date"}, level="ERROR")
        return
    if any(item != today for item in normalized_dates):
        st.error("Repository submissions only accept today's records. Past or future dates are blocked.")
        log_event(
            username,
            "input_validation_failed",
            {"source": source_label, "message": "Past/future record blocked", "today": str(today)},
            level="ERROR",
        )
        return

    is_valid, message = validate_financial_dataframe(df)
    if not is_valid:
        st.error(message)
        log_event(username, "input_validation_failed", {"source": source_label, "message": message}, level="ERROR")
        return

    SERVICE.save_shared_input(df, source_label, username)
    context = SERVICE.build_context(input_df=df)
    st.success(f"{source_label} was analyzed and shared with the dashboard.")
    log_event(username, "input_analyzed", {"source": source_label, "rows": len(df)})

    latest = context["dataframe"].iloc[-1]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Latest Revenue", f"{latest['revenue']:,.0f}")
    col2.metric("Latest Expenses", f"{latest['expenses']:,.0f}")
    col3.metric("Anomaly Score", f"{latest['anomaly_score']:.2f}")
    col4.metric("Risk Level", latest["risk_level"])

    st.subheader("Preview")
    st.dataframe(df, width="stretch")

    st.subheader("Insights")
    for insight in generate_basic_financial_insights(df):
        st.write(f"- {insight}")

    st.subheader("Shared Analysis Output")
    output_columns = [
        column
        for column in ["date", "transaction_id", "anomaly_score", "risk_level", "decision", "zscore_anomaly", "payment_status"]
        if column in context["dataframe"].columns
    ]
    st.dataframe(
        context["dataframe"][output_columns],
        width="stretch",
    )


def render_structured_input(username: str) -> None:
    """Render file-based structured input workflow."""
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Structured Input")
    uploaded_file = st.file_uploader(
        "Upload CSV, JSON, or TXT with financial columns",
        type=["csv", "json", "txt"],
        key="structured_input_uploader",
    )
    if uploaded_file and st.button("Analyze Structured File", key="analyze_structured"):
        try:
            df = parse_uploaded_file(uploaded_file.name, uploaded_file.getvalue())
            analyze_and_share_dataframe(df, f"Structured file: {uploaded_file.name}", username)
        except Exception as exc:
            log_event(username, "structured_input_error", {"error": str(exc)}, level="ERROR")
            st.error(f"Could not analyze the uploaded file. Details: {exc}")
    st.markdown("</div>", unsafe_allow_html=True)


def render_unstructured_input(username: str) -> None:
    """Render unstructured text parsing workflow."""
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Unstructured Input")
    st.caption(
        "Paste invoice-style text or upload a text-based PDF/TXT invoice. The parser will extract date, invoice ID, total, paid amount, and related values into the standard schema."
    )
    invoice_file = st.file_uploader(
        "Upload invoice PDF or text document",
        type=["pdf", "txt"],
        key="unstructured_invoice_uploader",
    )
    raw_text = st.text_area("Paste unstructured financial text", height=220, key="unstructured_text")
    if st.button("Analyze Unstructured Text", key="analyze_unstructured"):
        try:
            extracted_text = raw_text
            source_label = "Unstructured text"
            if invoice_file is not None:
                extracted_text = extract_text_from_document(invoice_file.name, invoice_file.getvalue())
                source_label = f"Invoice document: {invoice_file.name}"
            if extracted_text:
                with st.expander("Extracted Document Text", expanded=False):
                    st.text_area("PDF/Text extraction preview", value=extracted_text, height=260, disabled=True, key="extracted_text_preview")
            df = parse_unstructured_financial_text(extracted_text)
            analyze_and_share_dataframe(df, source_label, username)
        except Exception as exc:
            log_event(username, "unstructured_input_error", {"error": str(exc)}, level="ERROR")
            st.error(f"Could not analyze the text input. Details: {exc}")
    st.markdown("</div>", unsafe_allow_html=True)


def render_manual_entry(username: str) -> None:
    """Render manual structured entry workflow."""
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Manual Entry")
    today = date.today()
    st.caption("Enter only today's records. Transaction IDs are auto-generated, locked, and increment from the last manual transaction.")
    record_count = st.number_input("Number of records", min_value=1, max_value=12, value=1, step=1)
    generated_transaction_ids = _get_next_manual_transaction_ids(int(record_count))
    entries: list[dict[str, object]] = []

    for index in range(int(record_count)):
        st.markdown(f"**Record {index + 1}**")
        col1, col2 = st.columns(2)
        date_value = col1.date_input(
            f"Date {index + 1}",
            value=today,
            min_value=today,
            max_value=today,
            key=f"manual_date_{index}",
        )
        transaction_id = generated_transaction_ids[index]
        col2.text_input(
            f"Transaction ID {index + 1}",
            value=transaction_id,
            key=f"manual_txn_{index}",
            disabled=True,
        )

        col3, col4 = st.columns(2)
        revenue = col3.number_input(f"Revenue {index + 1}", min_value=0.0, value=0.0, step=1000.0, key=f"manual_revenue_{index}")
        expenses = col4.number_input(f"Expenses {index + 1}", min_value=0.0, value=0.0, step=1000.0, key=f"manual_expenses_{index}")

        col5, col6 = st.columns(2)
        cash_flow = col5.number_input(f"Cash Flow {index + 1}", value=0.0, step=1000.0, key=f"manual_cash_{index}")
        customer_count = col6.number_input(f"Customers {index + 1}", min_value=0.0, value=0.0, step=1.0, key=f"manual_customers_{index}")

        col7, col8 = st.columns(2)
        receivables = col7.number_input(
            f"Receivables {index + 1}",
            min_value=0.0,
            value=0.0,
            step=500.0,
            key=f"manual_receivables_{index}",
        )
        marketing = col8.number_input(
            f"Marketing Spend {index + 1}",
            min_value=0.0,
            value=0.0,
            step=500.0,
            key=f"manual_marketing_{index}",
        )

        entries.append(
            {
                "date": str(date_value),
                "transaction_id": transaction_id,
                "revenue": revenue,
                "expenses": expenses,
                "cash_flow": cash_flow,
                "customer_count": customer_count,
                "accounts_receivable": receivables,
                "inventory": max(expenses * 0.15, 0.0),
                "marketing_spend": marketing,
            }
        )

    if st.button("Analyze Manual Entry", key="analyze_manual"):
        try:
            df = build_manual_entry_dataframe(entries)
            analyze_and_share_dataframe(df, "Manual entry", username)
        except Exception as exc:
            log_event(username, "manual_input_error", {"error": str(exc)}, level="ERROR")
            st.error(f"Could not analyze the manual entry. Details: {exc}")
    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    """Render the standalone data input webpage."""
    apply_classic_theme()
    username = require_login(DATABASE, "input_studio")
    user_profile = DATABASE.get_user_profile(username)
    permissions = ACCESS_CONTROL.permissions_for_role(user_profile.get("role", "viewer"))
    render_header(username)

    if not permissions.get("submit_data", False):
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Restricted Access")
        st.warning(
            "This workspace is read-only for your role. Viewer accounts can monitor the dashboard, but only admins and analysts can submit or replace shared financial data."
        )
        st.info(f"Current role: {user_profile.get('role', 'viewer').title()}")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    state = DATABASE.get_shared_input_state(tenant_id=int(user_profile.get("tenant_id", 1)))
    if state and state.get("is_active"):
        st.info(
            f"Current shared dataset: {state.get('source_label', 'submission')} by {state.get('username', 'user')} "
            f"at {state.get('updated_at', '')}"
        )

    tab1, tab2, tab3 = st.tabs(["Structured File", "Unstructured Text", "Manual Entry"])
    with tab1:
        render_structured_input(username)
    with tab2:
        render_unstructured_input(username)
    with tab3:
        render_manual_entry(username)


if __name__ == "__main__":
    main()
