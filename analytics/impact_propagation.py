from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import pandas as pd


@dataclass
class ImpactPropagationResult:
    chain_text: str
    nodes: list[dict[str, float | str]]
    edges: list[tuple[str, str]]


def build_financial_impact_graph(row: pd.Series) -> ImpactPropagationResult:
    """Build a simple dependency graph showing how anomalies propagate through metrics."""
    graph = nx.DiGraph()
    graph.add_edges_from(
        [
            ("revenue", "profit"),
            ("expenses", "profit"),
            ("profit", "cash_flow"),
            ("cash_flow", "risk"),
        ]
    )

    nodes = [
        {"metric": "revenue", "value": float(row["revenue"])},
        {"metric": "expenses", "value": float(row["expenses"])},
        {"metric": "profit", "value": float(row["profit"])},
        {"metric": "cash_flow", "value": float(row["cash_flow"])},
        {"metric": "risk", "value": float(row.get("risk_score", 0.0))},
    ]
    chain_text = (
        f"Revenue at {float(row['revenue']):,.0f} and expenses at {float(row['expenses']):,.0f} "
        f"drive profit to {float(row['profit']):,.0f}, which flows into cash flow at {float(row['cash_flow']):,.0f} "
        f"and results in risk pressure of {float(row.get('risk_score', 0.0)):.2f}."
    )
    return ImpactPropagationResult(
        chain_text=chain_text,
        nodes=nodes,
        edges=list(graph.edges()),
    )
