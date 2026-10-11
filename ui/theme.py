from __future__ import annotations

import streamlit as st


def apply_classic_theme() -> None:
    """Apply a vibrant premium-style theme to Streamlit pages."""
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at 8% 12%, rgba(0, 255, 200, 0.15), transparent 18%),
                radial-gradient(circle at 88% 10%, rgba(255, 122, 89, 0.18), transparent 18%),
                radial-gradient(circle at 52% 90%, rgba(79, 70, 229, 0.10), transparent 20%),
                linear-gradient(180deg, #fff8ef 0%, #fffefc 44%, #f4f8ff 100%);
            color: #182435;
        }
        .block-container {
            max-width: 1160px;
            padding-top: 1.6rem;
            padding-bottom: 3rem;
        }
        h1, h2, h3 {
            color: #162338;
            letter-spacing: -0.03em;
        }
        [data-testid="stSidebar"] {
            background:
                radial-gradient(circle at 18% 12%, rgba(56, 189, 248, 0.20), transparent 24%),
                radial-gradient(circle at 85% 20%, rgba(250, 204, 21, 0.14), transparent 28%),
                linear-gradient(180deg, #07111f 0%, #10243c 46%, #17395a 100%);
            border-right: 1px solid rgba(125, 211, 252, 0.16);
        }
        [data-testid="stSidebar"] * {
            color: #f8fbff !important;
        }
        [data-testid="stSidebar"] .stButton,
        [data-testid="stSidebar"] div[data-testid="stButton"] {
            width: 100% !important;
            display: block;
            flex: 1 1 100% !important;
            margin: 0 0 0.55rem 0 !important;
        }
        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button {
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            border-radius: 16px;
            min-height: 3.1rem;
            height: 3.1rem;
            display: flex !important;
            border: 1px solid rgba(125, 211, 252, 0.38);
            background: #f5f8fc;
            color: #0b2240 !important;
            font-weight: 700;
            letter-spacing: 0.01em;
            box-shadow: 0 14px 30px rgba(5, 16, 31, 0.24);
            justify-content: flex-start;
            padding-left: 1rem;
            padding-right: 1rem;
        }
        [data-testid="stSidebar"] .stButton > button *,
        [data-testid="stSidebar"] .stButton > button p,
        [data-testid="stSidebar"] .stButton > button span,
        [data-testid="stSidebar"] .stButton > button div,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button *,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button p,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button span,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button div {
            color: #0b2240 !important;
        }
        [data-testid="stSidebar"] .stButton > button:hover,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button:hover {
            border-color: rgba(250, 204, 21, 0.82);
            color: #06172b !important;
            background: #ffffff;
            transform: translateY(-1px);
        }
        [data-testid="stSidebar"] .stButton > button:hover *,
        [data-testid="stSidebar"] .stButton > button:hover p,
        [data-testid="stSidebar"] .stButton > button:hover span,
        [data-testid="stSidebar"] .stButton > button:hover div,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button:hover *,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button:hover p,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button:hover span,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button:hover div {
            color: #06172b !important;
        }
        [data-testid="stSidebar"] .stButton > button:disabled,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button:disabled {
            background: #e9eef5;
            color: #6f7d8f !important;
            border-color: rgba(255,255,255,0.22);
        }
        [data-testid="stSidebar"] .stButton > button:disabled *,
        [data-testid="stSidebar"] .stButton > button:disabled p,
        [data-testid="stSidebar"] .stButton > button:disabled span,
        [data-testid="stSidebar"] .stButton > button:disabled div,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button:disabled *,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button:disabled p,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button:disabled span,
        [data-testid="stSidebar"] div[data-testid="stButton"] > button:disabled div {
            color: #6f7d8f !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 14px;
            margin-top: 0.2rem;
            margin-bottom: 0.5rem;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary {
            color: #fff4e3 !important;
            font-weight: 700;
            padding-left: 0.15rem;
        }
        .section-card {
            border: 1px solid rgba(24, 36, 53, 0.08);
            border-radius: 22px;
            padding: 1rem 1.15rem;
            margin-bottom: 1rem;
            background: linear-gradient(180deg, rgba(255,255,255,0.88), rgba(248,250,252,0.84));
            box-shadow: 0 20px 48px rgba(22, 35, 56, 0.10);
            backdrop-filter: blur(12px);
        }
        .command-card {
            border-radius: 18px;
            padding: 0.9rem 1rem;
            margin-bottom: 1rem;
            background: linear-gradient(135deg, rgba(37, 99, 235, 0.28) 0%, rgba(16, 185, 129, 0.18) 62%, rgba(250, 204, 21, 0.14) 100%);
            border: 1px solid rgba(191, 219, 254, 0.22);
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.12), 0 16px 30px rgba(3, 10, 24, 0.18);
        }
        .command-card-title {
            font-size: 1rem;
            font-weight: 800;
            color: #ffffff;
        }
        .command-card-subtitle {
            font-size: 0.86rem;
            color: rgba(240, 248, 255, 0.82);
            margin-top: 0.18rem;
        }
        .command-section-title {
            margin: 0.7rem 0 0.55rem 0.1rem;
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: rgba(191, 219, 254, 0.9);
        }
        .kpi-ribbon {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.42rem 0.72rem;
            border-radius: 999px;
            background: rgba(14, 165, 233, 0.10);
            color: #0f4370;
            font-weight: 700;
            margin-right: 0.45rem;
            margin-bottom: 0.55rem;
        }
        .hero-card {
            border-radius: 26px;
            padding: 1.55rem 1.6rem;
            margin-bottom: 1.15rem;
            background:
                linear-gradient(135deg, rgba(5, 10, 29, 0.98) 0%, rgba(30, 64, 175, 0.96) 35%, rgba(8, 145, 178, 0.94) 68%, rgba(245, 158, 11, 0.92) 120%);
            color: #fffaf2;
            box-shadow: 0 30px 70px rgba(20, 32, 51, 0.22);
        }
        .hero-title {
            font-size: 2.25rem;
            font-weight: 800;
            margin-bottom: 0.3rem;
        }
        .hero-subtitle {
            font-size: 1rem;
            color: rgba(255, 248, 236, 0.88);
            max-width: 760px;
        }
        .stMetric {
            background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(241,245,249,0.92));
            border: 1px solid rgba(56, 189, 248, 0.18);
            padding: 0.85rem 1rem;
            border-radius: 18px;
            box-shadow: 0 14px 28px rgba(24, 36, 53, 0.08);
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
        }
        .stTabs [data-baseweb="tab"] {
            background: rgba(255,255,255,0.72);
            border: 1px solid rgba(24, 36, 53, 0.08);
            border-radius: 999px;
            padding: 0.55rem 1rem;
            color: #1b2a3d;
        }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, #0d4ed8 0%, #0ea5e9 42%, #14b8a6 100%);
            color: #ffffff !important;
            border-color: transparent !important;
            box-shadow: 0 12px 28px rgba(14, 165, 233, 0.28);
        }
        .stChatMessage {
            border-radius: 18px;
            padding: 0.85rem 1rem;
            margin-bottom: 0.65rem;
            border: 1px solid rgba(24, 36, 53, 0.08);
        }
        .stChatMessage[data-testid="stChatMessage-user"] {
            background: rgba(228, 240, 255, 0.95);
        }
        .stChatMessage[data-testid="stChatMessage-assistant"] {
            background: rgba(255, 250, 241, 0.97);
        }
        .chat-wrap {
            max-height: 520px;
            overflow-y: auto;
            scroll-behavior: smooth;
            padding-right: 0.25rem;
        }
        .status-pill {
            display: inline-block;
            padding: 0.42rem 0.8rem;
            border-radius: 999px;
            background: rgba(14, 165, 233, 0.18);
            color: #0d4a78;
            font-weight: 600;
            margin-bottom: 1rem;
        }
        .feature-chip {
            display: inline-block;
            margin: 0.18rem 0.32rem 0.18rem 0;
            padding: 0.46rem 0.78rem;
            border-radius: 999px;
            background: rgba(13, 78, 216, 0.12);
            color: #123f72;
            font-size: 0.92rem;
            font-weight: 600;
        }
        .prompt-card {
            border: 1px solid rgba(59, 130, 246, 0.14);
            background: linear-gradient(180deg, rgba(239,246,255,0.95), rgba(255,247,237,0.92));
            border-radius: 16px;
            padding: 0.9rem 1rem;
            min-height: 118px;
        }
        .chat-shell {
            display: grid;
            grid-template-columns: minmax(220px, 300px) 1fr;
            gap: 1rem;
            align-items: start;
            margin-bottom: 1rem;
        }
        .chat-panel {
            border: 1px solid rgba(24, 36, 53, 0.08);
            border-radius: 22px;
            padding: 1rem 1.1rem;
            background: rgba(255,255,255,0.86);
            box-shadow: 0 16px 36px rgba(24, 36, 53, 0.08);
        }
        .chat-panel-title {
            font-size: 1rem;
            font-weight: 800;
            color: #13233b;
            margin-bottom: 0.65rem;
        }
        .insight-banner {
            background: linear-gradient(135deg, rgba(37,99,235,0.12), rgba(20,184,166,0.14));
            color: #123f72;
            border-radius: 16px;
            padding: 0.85rem 0.95rem;
            margin-bottom: 1rem;
            border: 1px solid rgba(59,130,246,0.10);
            font-weight: 600;
        }
        .master-draft {
            background: linear-gradient(135deg, rgba(13,22,38,0.96) 0%, rgba(22,50,87,0.96) 100%);
            color: #fff;
            border-radius: 22px;
            padding: 1.2rem 1.25rem;
        }
        .floating-chat-launcher {
            position: fixed;
            right: 1.2rem;
            bottom: 1.35rem;
            z-index: 9999;
            width: 68px;
            height: 68px;
            border-radius: 20px;
            background: linear-gradient(135deg, #10233f 0%, #0b4d7d 55%, #12c2a3 130%);
            color: #fff8ef !important;
            text-decoration: none !important;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 18px 38px rgba(16, 35, 63, 0.28);
            border: 1px solid rgba(255,255,255,0.22);
            font-size: 0.8rem;
            font-weight: 700;
            text-align: center;
            line-height: 1.1;
        }
        .floating-chat-launcher:hover {
            transform: translateY(-2px);
        }
        .alert-overlay {
            border-radius: 22px;
            padding: 1rem 1.1rem;
            margin: 0.8rem 0 1rem 0;
            background: linear-gradient(135deg, rgba(159, 18, 57, 0.95) 0%, rgba(220, 38, 38, 0.92) 55%, rgba(251, 146, 60, 0.90) 150%);
            color: #fff7ee;
            box-shadow: 0 20px 44px rgba(185, 28, 28, 0.24);
        }
        .alert-title {
            font-size: 1.05rem;
            font-weight: 800;
            margin-bottom: 0.25rem;
        }
        .chat-dock {
            border-radius: 24px;
            padding: 1rem 1rem 0.8rem 1rem;
            margin-top: 1rem;
            background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(240,248,255,0.94));
            border: 1px solid rgba(24, 36, 53, 0.08);
            box-shadow: 0 18px 36px rgba(24, 36, 53, 0.10);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
