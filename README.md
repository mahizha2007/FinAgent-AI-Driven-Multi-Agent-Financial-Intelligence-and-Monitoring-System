# AI-Driven Multi-Agent Financial Monitoring System with Rational Agent Chatbot

This project is a Python-only financial monitoring platform built with Streamlit, scikit-learn, PyTorch, Prophet, SHAP, and SQLite. It ingests financial data, engineers features, detects anomalies with a hybrid model, forecasts revenue and expenses, explains anomalies, simulates stress scenarios, computes XIRR, stores an audit trail, and exposes a rational-agent chatbot.

## Features

- CSV plus simulated ERP ingestion with APScheduler auto-refresh
- Preprocessing with missing-value handling, normalization, and feature engineering
- Hybrid anomaly detection using Isolation Forest and a PyTorch autoencoder
- Modular multi-agent architecture:
  - `AnomalyAgent`
  - `RiskAgent`
  - `ExplanationAgent`
  - `ForecastAgent`
  - `SimulationAgent`
  - `ChatAgent`
- Rational decision engine with `ALERT`, `IGNORE`, and `ASK_USER`
- Stress testing and natural-language scenario simulation
- Custom XIRR implementation from scratch
- SHAP-based explainability
- Streamlit dashboard with chatbot, charts, alerts, and anomaly tables
- SQLite audit trail and user memory

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
streamlit run ui/app.py
```

## Example Chat Prompts

- `What is the latest risk level?`
- `Show anomalies`
- `Which transaction has the highest anomaly score?`
- `Forecast revenue`
- `Compute XIRR`
- `What if revenue drops 20% and expenses increase 10%?`

## SQLite Audit Trail

Database file: `data/financial_monitor.db`

Tables:

- `anomalies`
- `agent_decisions`
- `user_queries`
