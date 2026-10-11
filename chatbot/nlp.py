from __future__ import annotations

import re
from dataclasses import dataclass


INTENT_PATTERNS = {
    "greeting": [
        r"^(hi|hello|hey|yo|good (morning|afternoon|evening))\b",
    ],
    "thanks": [
        r"\b(thanks|thank you|thx|appreciate it)\b",
    ],
    "help": [
        r"\b(help|assist|support me|guide me)\b",
        r"\bwhat can i ask\b",
    ],
    "identity": [
        r"\b(who are you|what are you|introduce yourself)\b",
    ],
    "capabilities": [
        r"\b(capabilities|features|functions|skills)\b",
        r"\bwhat all can you do\b",
        r"\bwhat can you do\b",
    ],
    "current_summary": [
        r"\b(summarize|summary|snapshot|current state|overall status|what's going on)\b",
    ],
    "off_topic": [
        r"\b(weather|movie|music|song|cricket|football|love|joke|meme|birthday|gaming)\b",
        r"\bhow are you\b",
    ],
    "latest_decision": [
        r"\b(latest|current|recent)\b.*\b(decision|action|verdict)\b",
        r"\bwhat should we do\b",
    ],
    "risk_probability": [
        r"\b(risk probability|probability of risk|bayesian risk|likelihood of risk)\b",
        r"\bhow risky\b",
    ],
    "impact": [
        r"\b(financial impact|impact|counterfactual|expected profit|actual profit)\b",
        r"\b(loss|gain)\b",
    ],
    "forecast_revenue": [
        r"\bforecast\b.*\brevenue\b",
        r"\brevenue\b.*\bforecast\b",
    ],
    "forecast_expense": [
        r"\bforecast\b.*\b(expense|expenses|cost)\b",
        r"\b(expense|expenses|cost)\b.*\bforecast\b",
    ],
    "period_compare": [
        r"\b(compare|comparison|versus|vs)\b.*\b(revenue|sales|profit|expenses)\b",
        r"\b(january|february|march|april)\b.*\b(january|february|march|april)\b",
    ],
    "top_anomaly": [
        r"\b(top|highest|largest|strongest)\b.*\banomal",
        r"\bmost anomal",
    ],
    "count_anomalies": [
        r"\bhow many\b.*\banomal",
        r"\bcount\b.*\banomal",
    ],
    "show_anomalies": [
        r"\b(show|list|display)\b.*\banomal",
        r"\bflagged transactions?\b",
    ],
    "invoice_status": [
        r"\b(invoice|bill)\b.*\b(status|paid|unpaid|partial|outstanding|balance)\b",
        r"\b(partially paid|partial payment|unpaid|outstanding)\b",
    ],
    "reasoning": [
        r"\b(why|reason|reasoning|trace|explain)\b.*\b(alert|decision|risk)\b",
    ],
    "metric_explanation": [
        r"\bwhat is\b.*\b(revenue|expenses|profit|margin|risk probability|anomaly score|cash flow)\b",
        r"\bexplain\b.*\b(revenue|expenses|profit|margin|risk probability|anomaly score|cash flow)\b",
    ],
    "scenario": [
        r"\bwhat if\b",
        r"\brevenue\b.*\bdrops?\b",
        r"\bexpenses?\b.*\b(increase|rise|grow)\b",
    ],
    "xirr": [
        r"\b(xirr|irr)\b",
    ],
    "alert_history": [
        r"\b(alert history|decision history|past alerts)\b",
    ],
    "master_draft": [
        r"\b(master draft|executive brief|board brief|summary report|download report|command brief)\b",
    ],
    "logs": [
        r"\b(log|logs|audit trail|history)\b",
        r"\bdownload\b.*\b(log|logs|audit)\b",
    ],
    "training_data": [
        r"\b(training data|training dataset|model dataset|how much data)\b",
        r"\bhow many rows\b.*\b(train|training)\b",
    ],
    "access_control": [
        r"\b(role|permission|access|viewer|admin|reviewer|analyst)\b",
        r"\bwhat can i access\b",
    ],
    "recommendations": [
        r"\b(recommend|next steps|what should we do next|action plan)\b",
    ],
}


@dataclass
class NLPParseResult:
    intent: str
    confidence: float
    entities: dict[str, str]


def parse_financial_query(query: str) -> NLPParseResult:
    """Infer the user's intent with lightweight rule-based NLP."""
    lower = query.lower().strip()
    entities: dict[str, str] = {}
    pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", lower)
    if pct_match:
        entities["percentage"] = pct_match.group(1)
    txn_match = re.search(r"\b([A-Z]{2,5}-?\d{3,6}|TXN-\d+|TRN-\d+|EXP-\d+)\b", query, flags=re.IGNORECASE)
    if txn_match:
        entities["transaction_id"] = txn_match.group(1).upper()
    metric_match = re.search(
        r"\b(revenue|expenses|expense|profit|margin|cash flow|cashflow|risk probability|risk|anomaly score|anomaly|forecast|logs|invoice|outstanding)\b",
        lower,
    )
    if metric_match:
        entities["metric"] = metric_match.group(1).replace("cashflow", "cash flow")
    question_type_match = re.match(r"^(what|why|how|can|should|when|where|who|is|are|do|does)\b", lower)
    if question_type_match:
        entities["question_type"] = question_type_match.group(1)
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, lower):
                return NLPParseResult(intent=intent, confidence=0.92, entities=entities)
    keyword_hits = sum(
        1
        for word in ["anomaly", "risk", "forecast", "scenario", "profit", "revenue", "expense", "decision", "alert", "invoice", "cash flow", "margin", "logs", "dashboard"]
        if word in lower
    )
    if keyword_hits >= 2:
        return NLPParseResult(intent="general_finance_question", confidence=0.76, entities=entities)
    if question_type_match:
        return NLPParseResult(intent="general_question", confidence=0.55, entities=entities)
    confidence = 0.72 if keyword_hits >= 1 else 0.4
    return NLPParseResult(intent="fallback", confidence=confidence, entities=entities)
