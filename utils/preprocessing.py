from __future__ import annotations

import json
import re
from dataclasses import dataclass
from io import BytesIO
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency at runtime
    PdfReader = None


FEATURE_COLUMNS = [
    "revenue",
    "expenses",
    "cash_flow",
    "customer_count",
    "accounts_receivable",
    "inventory",
    "marketing_spend",
    "profit",
    "revenue_growth",
    "expense_ratio",
    "profit_margin",
]

BASE_REQUIRED_COLUMNS = [
    "date",
    "transaction_id",
    "revenue",
    "expenses",
    "cash_flow",
    "customer_count",
    "accounts_receivable",
    "inventory",
    "marketing_spend",
]

OPTIONAL_NUMERIC_COLUMNS = [
    "outstanding_amount",
]

CATEGORICAL_COLUMNS = [
    "payment_status",
]


@dataclass
class PreprocessingOutput:
    cleaned_df: pd.DataFrame
    feature_matrix: np.ndarray
    feature_names: list[str]
    scaler: StandardScaler


def _ensure_required_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure all required base columns exist before sanitation."""
    result = df.copy()
    for column in BASE_REQUIRED_COLUMNS:
        if column not in result.columns:
            result[column] = np.nan
    return result


def sanitize_financial_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Sanitize user-provided financial data and make it model-safe."""
    result = _ensure_required_columns(df.copy()).copy()
    result = result.replace(r"^\s*$", np.nan, regex=True)

    if "date" in result.columns:
        result.loc[:, "date"] = pd.to_datetime(result["date"], errors="coerce")
        if result["date"].notna().sum() == 0:
            result.loc[:, "date"] = pd.date_range(end=pd.Timestamp.today().normalize(), periods=len(result), freq="MS")
        else:
            fallback_dates = pd.date_range(
                start=result["date"].dropna().min(),
                periods=len(result),
                freq="MS",
            )
            result.loc[:, "date"] = result["date"].fillna(pd.Series(fallback_dates, index=result.index))

    if "transaction_id" in result.columns:
        result.loc[:, "transaction_id"] = result["transaction_id"].astype(str).replace({"nan": np.nan, "None": np.nan})
        for index in result.index:
            if pd.isna(result.at[index, "transaction_id"]) or not str(result.at[index, "transaction_id"]).strip():
                result.at[index, "transaction_id"] = f"AUTO-{index + 1:03d}"

    numeric_columns = [col for col in BASE_REQUIRED_COLUMNS if col not in {"date", "transaction_id"}]
    for column in numeric_columns:
        result.loc[:, column] = pd.to_numeric(result[column], errors="coerce")
        if result[column].notna().sum() == 0:
            result.loc[:, column] = 0.0
        else:
            result.loc[:, column] = result[column].fillna(result[column].median())

    for column in OPTIONAL_NUMERIC_COLUMNS:
        if column in result.columns:
            result.loc[:, column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)

    for column in CATEGORICAL_COLUMNS:
        if column in result.columns:
            result.loc[:, column] = result[column].fillna("").astype(str).str.strip()

    result = result.dropna(how="all").reset_index(drop=True)
    return result.sort_values("date").reset_index(drop=True)


def load_csv_data(csv_path: str | Path) -> pd.DataFrame:
    """Load the baseline financial dataset from CSV."""
    df = pd.read_csv(csv_path, parse_dates=["date"])
    numeric_columns = [col for col in df.columns if col not in {"date", "transaction_id"}]
    df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors="coerce")
    return sanitize_financial_dataframe(df)


def simulate_erp_api(last_date: pd.Timestamp, periods: int = 1) -> pd.DataFrame:
    """Simulate ERP records for scheduled refreshes."""
    rows = []
    base_revenue = 252000
    base_expenses = 146500
    for offset in range(1, periods + 1):
        current_date = (last_date + pd.offsets.MonthBegin(offset)).normalize()
        revenue = base_revenue + (offset * 5200)
        expenses = base_expenses + (offset * 2800)
        rows.append(
            {
                "date": current_date,
                "transaction_id": f"ERP-{current_date.strftime('%Y%m')}",
                "revenue": revenue,
                "expenses": expenses,
                "cash_flow": revenue - expenses - 5500,
                "customer_count": 720 + (offset * 10),
                "accounts_receivable": 32500 + (offset * 700),
                "inventory": 15800 + (offset * 180),
                "marketing_spend": 21000 + (offset * 220),
            }
        )
    return pd.DataFrame(rows)


def append_erp_refresh(df: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    """Append simulated ERP data and keep the freshest record per transaction/date."""
    refreshed = pd.concat([df, simulate_erp_api(df["date"].max(), periods)], ignore_index=True)
    return refreshed.drop_duplicates(subset=["date", "transaction_id"], keep="last").sort_values("date").reset_index(drop=True)


def preprocess_financial_data(df: pd.DataFrame) -> PreprocessingOutput:
    """Clean, enrich, and scale financial data for downstream models."""
    processed = engineer_financial_features(df)
    numeric_columns = [col for col in FEATURE_COLUMNS if col in processed.columns]
    processed[numeric_columns] = processed[numeric_columns].fillna(processed[numeric_columns].median()).fillna(0.0)

    feature_frame = processed[FEATURE_COLUMNS].copy()
    scaler = StandardScaler()
    feature_matrix = scaler.fit_transform(feature_frame)
    return PreprocessingOutput(processed, feature_matrix, FEATURE_COLUMNS, scaler)


def engineer_financial_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create financial features without fitting a scaler."""
    processed = sanitize_financial_dataframe(df)
    numeric_columns = [col for col in (BASE_REQUIRED_COLUMNS + OPTIONAL_NUMERIC_COLUMNS) if col in processed.columns and col not in {"date", "transaction_id"}]
    processed[numeric_columns] = processed[numeric_columns].fillna(processed[numeric_columns].median()).fillna(0.0)
    processed["profit"] = processed["revenue"] - processed["expenses"]
    processed["revenue_growth"] = processed["revenue"].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    processed["expense_ratio"] = (processed["expenses"] / processed["revenue"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    processed["profit_margin"] = (processed["profit"] / processed["revenue"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return processed


def transform_financial_data(df: pd.DataFrame, scaler: StandardScaler) -> PreprocessingOutput:
    """Transform inference data with an already-fitted scaler."""
    processed = engineer_financial_features(df)
    feature_frame = processed[FEATURE_COLUMNS].copy()
    feature_matrix = scaler.transform(feature_frame)
    return PreprocessingOutput(processed, feature_matrix, FEATURE_COLUMNS, scaler)


def validate_financial_dataframe(df: pd.DataFrame) -> tuple[bool, str]:
    """Validate uploaded financial data against required columns."""
    required_identity_columns = ["date", "transaction_id"]
    missing_columns = [column for column in required_identity_columns if column not in df.columns]
    if missing_columns:
        return False, f"Missing required columns: {', '.join(missing_columns)}"
    if df.empty:
        return False, "Uploaded file is empty."
    sanitized = sanitize_financial_dataframe(df)
    if sanitized.empty:
        return False, "Uploaded file does not contain usable financial rows."
    transaction_ids = sanitized["transaction_id"].fillna("").astype(str).str.strip()
    blank_ids = transaction_ids.eq("")
    if blank_ids.any():
        return False, "Every record must have a non-empty transaction ID."
    duplicate_ids = transaction_ids[transaction_ids.duplicated(keep=False)].unique().tolist()
    if duplicate_ids:
        duplicate_list = ", ".join(sorted(duplicate_ids))
        return False, f"Duplicate transaction IDs are not allowed: {duplicate_list}"
    return True, "Validation successful."


def parse_uploaded_file(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    """Parse CSV, JSON, or TXT uploads into a financial DataFrame."""
    suffix = Path(file_name).suffix.lower()
    raw_text = file_bytes.decode("utf-8")

    if suffix == ".csv":
        df = pd.read_csv(StringIO(raw_text))
    elif suffix == ".json":
        payload = json.loads(raw_text)
        df = pd.DataFrame(payload)
    elif suffix == ".txt":
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        df = pd.read_csv(StringIO("\n".join(lines)))
    else:
        raise ValueError("Unsupported file type. Please upload CSV, JSON, or TXT.")

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return sanitize_financial_dataframe(df)


def extract_text_from_document(file_name: str, file_bytes: bytes) -> str:
    """Extract plain text from a PDF or text-like document."""
    suffix = Path(file_name).suffix.lower()
    if suffix == ".pdf":
        if PdfReader is None:
            raise ValueError("PDF support requires the 'pypdf' package. Install dependencies again to enable it.")
        reader = PdfReader(BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    return file_bytes.decode("utf-8", errors="ignore")


def _extract_first_date(text: str) -> str | None:
    """Extract the first recognizable date from raw invoice text."""
    patterns = [
        r"\b(20\d{2}[-/]\d{2}[-/]\d{2})\b",
        r"\b(\d{2}[-/]\d{2}[-/](?:20)?\d{2})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            parsed = pd.to_datetime(match.group(1), errors="coerce", dayfirst=False)
            if pd.notna(parsed):
                return str(parsed.date())
    return None


def _extract_invoice_identifier(text: str) -> str | None:
    """Extract a likely invoice or transaction identifier."""
    patterns = [
        r"(?:invoice\s*(?:id|number|no|#)|bill\s*(?:id|number|no|#)|transaction\s*(?:id|number|#))\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/]*\d[A-Z0-9\-\/]*)",
        r"\b((?:(?:INV|BILL|TXN|TRN)[A-Z0-9\-\/]*\d[A-Z0-9\-\/]*))\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def _extract_labeled_amount(text: str, labels: list[str]) -> float | None:
    """Extract the first amount associated with one of the provided labels."""
    for label in labels:
        match = re.search(
            rf"{label}\s*[:\-]?\s*(?:INR|Rs\.?|USD|\$|₹)?\s*[^0-9\-]*([0-9,]+(?:\.\d{{1,2}})?)",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            cleaned = match.group(1).replace(",", "")
            try:
                return float(cleaned)
            except ValueError:
                continue
    return None


def _normalize_invoice_text(text: str) -> str:
    """Normalize raw invoice text while preserving record boundaries."""
    normalized_source = (text or "").replace("\r", "\n")
    normalized_source = normalized_source.replace("\xa0", " ")
    normalized_source = re.sub(r"[■▪●•]", " ", normalized_source)
    normalized_source = re.sub(r"(?<=\d)\s+(?=[\d,])", "", normalized_source)
    normalized_source = re.sub(r"(?i)\b([A-Z]{2,})\s*-\s*(\d{2,})\b", r"\1-\2", normalized_source)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized_source.splitlines()]
    return "\n".join(line for line in lines if line)


def _split_invoice_blocks(text: str) -> list[str]:
    """Split a pasted invoice document into one or more invoice-like blocks."""
    normalized = _normalize_invoice_text(text)
    if not normalized:
        return []

    marker_pattern = re.compile(
        r"(?i)(?=(?:^|\n|\s)(?:invoice\s*(?:id|number|no)?|bill\s*(?:id|number|no)?|transaction\s*(?:id|number|no)?)\s*[:#-])"
    )
    matches = list(marker_pattern.finditer(normalized))
    if not matches:
        return [normalized]

    blocks: list[str] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        block = normalized[start:end].strip()
        if block:
            blocks.append(block)
    return blocks or [normalized]


def _extract_line_item_total(text: str) -> float | None:
    """Estimate a total by summing labeled line items when no invoice total is found."""
    item_values: list[float] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.search(r"(?i)\b(total|final amount|paid amount|amount paid|paid|balance|status|date|invoice|bill|customer|client)\b", line):
            continue
        match = re.search(r"([0-9,]+(?:\.\d{1,2})?)\s*$", line)
        if not match:
            continue
        try:
            item_values.append(float(match.group(1).replace(",", "")))
        except ValueError:
            continue
    return sum(item_values) if item_values else None


def _extract_payment_status(text: str) -> str:
    """Extract a normalized payment status from invoice text."""
    match = re.search(r"(?i)\bstatus\s*[:\-]?\s*([A-Za-z ]+)", text)
    if match:
        status = re.sub(r"\s+", " ", match.group(1)).strip().lower()
        if "partial" in status:
            return "PARTIALLY_PAID"
        if "unpaid" in status or "overdue" in status or "due" == status:
            return "UNPAID"
        if "paid" in status:
            return "PAID"
    if re.search(r"(?i)\bbalance\s*[:\-]?\s*[1-9]", text) or re.search(r"(?i)\boutstanding\s*[:\-]?\s*[1-9]", text):
        return "PARTIALLY_PAID"
    if re.search(r"(?i)\bpaid\s*[:\-]?\s*0+(?:\.0+)?\b", text):
        return "UNPAID"
    return "PAID"


def _build_invoice_record(block_text: str, fallback_index: int) -> dict[str, Any]:
    """Convert one invoice-like text block into a standard financial record."""
    invoice_date = _extract_first_date(block_text)
    transaction_id = _extract_invoice_identifier(block_text) or f"INVOICE-AUTO-{fallback_index:03d}"
    revenue = _extract_labeled_amount(
        block_text,
        [
            "grand total",
            "total amount",
            "invoice total",
            "amount due",
            "net amount",
            "final amount",
            "service charges",
            "consulting services",
            "total",
        ],
    )
    if revenue is None:
        revenue = _extract_line_item_total(block_text)
    paid_amount = _extract_labeled_amount(
        block_text,
        ["paid amount", "payment received", "cash received", "amount paid", "paid"],
    )
    balance_amount = _extract_labeled_amount(
        block_text,
        ["balance due", "outstanding balance", "balance", "due amount"],
    )
    payment_status = _extract_payment_status(block_text)
    expenses = _extract_labeled_amount(
        block_text,
        ["expense", "cost", "subtotal", "taxable amount", "tax"],
    )

    revenue_value = revenue if revenue is not None else 0.0
    cash_flow_value = paid_amount if paid_amount is not None else 0.0
    receivable_value = balance_amount if balance_amount is not None else max(revenue_value - cash_flow_value, 0.0)
    if payment_status == "UNPAID":
        cash_flow_value = 0.0
        receivable_value = max(revenue_value, receivable_value)
    elif payment_status == "PARTIALLY_PAID":
        receivable_value = max(receivable_value, max(revenue_value - cash_flow_value, 0.0))
    else:
        receivable_value = 0.0 if cash_flow_value >= revenue_value else receivable_value

    return {
        "date": invoice_date or pd.Timestamp.today().date().isoformat(),
        "transaction_id": transaction_id,
        "revenue": revenue_value,
        "expenses": expenses if expenses is not None else 0.0,
        "cash_flow": cash_flow_value,
        "customer_count": 1.0,
        "accounts_receivable": receivable_value,
        "inventory": 0.0,
        "marketing_spend": 0.0,
        "payment_status": payment_status,
        "outstanding_amount": receivable_value,
    }


def parse_invoice_like_text(text: str) -> pd.DataFrame:
    """Parse invoice-style text into the standard financial schema."""
    blocks = _split_invoice_blocks(text)
    if not blocks:
        raise ValueError("The invoice text is empty.")

    records = [_build_invoice_record(block, index + 1) for index, block in enumerate(blocks)]
    df = pd.DataFrame(records)
    df.loc[:, "date"] = pd.to_datetime(df["date"], errors="coerce")
    return sanitize_financial_dataframe(df)


def build_manual_entry_dataframe(entries: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a validated DataFrame from manual-entry records."""
    df = pd.DataFrame(entries)
    if "date" in df.columns:
        df.loc[:, "date"] = pd.to_datetime(df["date"], errors="coerce")
    sanitized = sanitize_financial_dataframe(df)
    transaction_ids = sanitized["transaction_id"].fillna("").astype(str).str.strip()
    duplicate_ids = transaction_ids[transaction_ids.duplicated(keep=False)].unique().tolist()
    if duplicate_ids:
        duplicate_list = ", ".join(sorted(duplicate_ids))
        raise ValueError(f"Manual entry transaction IDs must be unique. Duplicate values found: {duplicate_list}")
    return sanitized


def parse_unstructured_financial_text(text: str) -> pd.DataFrame:
    """Parse unstructured finance text blocks or invoice-like text into a structured DataFrame.

    Expected style per line:
    2026-04-01 | TXN-4001 | revenue=250000 | expenses=140000 | cash_flow=52000 | customer_count=730 |
    accounts_receivable=33000 | inventory=15500 | marketing_spend=21000
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("No usable text was found to parse.")

    has_pipe_records = any("|" in line for line in lines)
    if not has_pipe_records:
        return parse_invoice_like_text(text)

    records: list[dict[str, Any]] = []
    numeric_fields = {
        "revenue",
        "expenses",
        "cash_flow",
        "customer_count",
        "accounts_receivable",
        "inventory",
        "marketing_spend",
    }

    for line in lines:
        parts = [part.strip() for part in line.split("|") if part.strip()]
        if len(parts) < 2:
            continue
        record: dict[str, Any] = {
            "date": parts[0],
            "transaction_id": parts[1],
        }
        for part in parts[2:]:
            if "=" not in part:
                continue
            key, value = [item.strip() for item in part.split("=", 1)]
            if key in numeric_fields:
                cleaned = re.sub(r"[^0-9.\-]", "", value)
                record[key] = float(cleaned) if cleaned else None
            else:
                record[key] = value
        records.append(record)

    df = pd.DataFrame(records)
    if "date" in df.columns:
        df.loc[:, "date"] = pd.to_datetime(df["date"], errors="coerce")
    return sanitize_financial_dataframe(df)


def compute_zscore_anomalies(df: pd.DataFrame, columns: list[str] | None = None, threshold: float = 2.5) -> pd.DataFrame:
    """Compute simple z-score anomaly flags for uploaded or baseline data."""
    result = df.copy()
    target_columns = columns or ["revenue", "expenses", "cash_flow"]
    zscore_frame = pd.DataFrame(index=result.index)
    for column in target_columns:
        series = pd.to_numeric(result[column], errors="coerce").fillna(result[column].median())
        std = series.std(ddof=0) or 1.0
        zscore_frame[f"{column}_zscore"] = (series - series.mean()) / std
    result["zscore_anomaly"] = (zscore_frame.abs().max(axis=1) >= threshold).astype(int)
    result["zscore"] = zscore_frame.abs().max(axis=1)
    return result


def apply_invoice_payment_rules(df: pd.DataFrame) -> pd.DataFrame:
    """Promote unpaid and partially paid invoice records to business anomalies."""
    result = df.copy()
    if "payment_status" not in result.columns:
        return result

    normalized_status = result["payment_status"].fillna("").astype(str).str.upper().str.strip()
    partial_mask = normalized_status.eq("PARTIALLY_PAID")
    unpaid_mask = normalized_status.eq("UNPAID")

    if "anomaly_score" in result.columns:
        result.loc[partial_mask, "anomaly_score"] = result.loc[partial_mask, "anomaly_score"].clip(lower=0.78)
        result.loc[unpaid_mask, "anomaly_score"] = result.loc[unpaid_mask, "anomaly_score"].clip(lower=0.90)
    if "anomaly_label" in result.columns:
        result.loc[partial_mask | unpaid_mask, "anomaly_label"] = 1
    if "zscore_anomaly" in result.columns:
        result.loc[partial_mask | unpaid_mask, "zscore_anomaly"] = 1
    if "risk_score" in result.columns:
        result.loc[partial_mask, "risk_score"] = result.loc[partial_mask, "risk_score"].clip(lower=0.72)
        result.loc[unpaid_mask, "risk_score"] = result.loc[unpaid_mask, "risk_score"].clip(lower=0.88)
    if "risk_level" in result.columns:
        result.loc[partial_mask, "risk_level"] = "HIGH"
        result.loc[unpaid_mask, "risk_level"] = "HIGH"

    result.loc[partial_mask | unpaid_mask, "payment_anomaly"] = 1
    result.loc[~(partial_mask | unpaid_mask), "payment_anomaly"] = 0
    return result


def dampen_benign_profitable_records(df: pd.DataFrame, baseline_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Reduce anomaly severity for clearly healthy paid/profitable low-scale records.

    This prevents tiny manual entries from being treated as critical anomalies just
    because they are far from the historical enterprise-scale baseline.
    """
    result = df.copy()
    if result.empty:
        return result

    baseline = baseline_df.copy() if baseline_df is not None and not baseline_df.empty else result.copy()
    baseline_revenue_median = float(pd.to_numeric(baseline.get("revenue", 0.0), errors="coerce").fillna(0.0).median())
    small_scale_cutoff = baseline_revenue_median * 0.08 if baseline_revenue_median > 0 else float("inf")

    profit = pd.to_numeric(result.get("profit", 0.0), errors="coerce").fillna(0.0)
    revenue = pd.to_numeric(result.get("revenue", 0.0), errors="coerce").fillna(0.0)
    expense_ratio = pd.to_numeric(result.get("expense_ratio", 0.0), errors="coerce").fillna(0.0)
    profit_margin = pd.to_numeric(result.get("profit_margin", 0.0), errors="coerce").fillna(0.0)
    receivables = pd.to_numeric(result.get("accounts_receivable", 0.0), errors="coerce").fillna(0.0)
    zscore_flags = pd.to_numeric(result.get("zscore_anomaly", 0), errors="coerce").fillna(0).astype(int)
    payment_status = result.get("payment_status", pd.Series([""] * len(result), index=result.index)).fillna("").astype(str).str.upper().str.strip()

    benign_mask = (
        (revenue > 0)
        & (revenue <= small_scale_cutoff)
        & (profit > 0)
        & (expense_ratio <= 0.35)
        & (profit_margin >= 0.20)
        & (receivables <= 0)
        & (~payment_status.isin(["UNPAID", "PARTIALLY_PAID"]))
        & (zscore_flags == 0)
    )

    if "anomaly_score" in result.columns:
        result.loc[benign_mask, "anomaly_score"] = result.loc[benign_mask, "anomaly_score"].clip(upper=0.34)
    if "anomaly_label" in result.columns:
        result.loc[benign_mask, "anomaly_label"] = 0
    if "risk_score" in result.columns:
        result.loc[benign_mask, "risk_score"] = result.loc[benign_mask, "risk_score"].clip(upper=0.30)
    if "risk_level" in result.columns:
        result.loc[benign_mask, "risk_level"] = "LOW"
    if "decision" in result.columns:
        result.loc[benign_mask, "decision"] = "IGNORE"
    result.loc[benign_mask, "benign_scale_adjustment"] = 1
    result.loc[~benign_mask, "benign_scale_adjustment"] = 0
    return result


def generate_basic_financial_insights(df: pd.DataFrame) -> list[str]:
    """Generate lightweight financial insights for uploaded data."""
    enriched = preprocess_financial_data(df).cleaned_df
    latest = enriched.iloc[-1]
    previous = enriched.iloc[-2] if len(enriched) > 1 else latest
    insights = [
        f"Latest profit margin is {latest['profit_margin']:.2%}.",
        f"Revenue changed by {latest['revenue_growth']:.2%} versus the previous period.",
        f"Expense ratio is {latest['expense_ratio']:.2%}, compared with {previous['expense_ratio']:.2%} previously.",
    ]
    return insights
