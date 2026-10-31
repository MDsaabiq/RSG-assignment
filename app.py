# app.py
"""
Streamlit Web Interface for AI Sales BI Assistant.

A pure frontend client connecting to the deployed FastAPI backend on Render.
Displays natural language answers, supporting data tables, SQL inspectability,
and execution source citations (Direct Verified SQL vs Dynamic LLM Text-to-SQL).
"""

import os
import threading
import httpx
import streamlit as st
import pandas as pd

# Backend API Configuration (Defaults to Render deployment)
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "https://rsg-assignment.onrender.com").rstrip("/")

st.set_page_config(
    page_title="Sales BI Assistant",
    page_icon="📊",
    layout="wide"
)


def _wake_backend():
    """Background worker that pings the Render backend to wake it from spin-down."""
    try:
        httpx.get(f"{BACKEND_API_URL}/health", timeout=60.0)
    except Exception:
        pass


# Automatically wake up Render on app startup / page visit without blocking UI
if "backend_woken" not in st.session_state:
    st.session_state["backend_woken"] = True
    threading.Thread(target=_wake_backend, daemon=True).start()


@st.cache_data(ttl=30)
def get_service_status() -> bool:
    """Quick check for live backend status with short timeout."""
    try:
        resp = httpx.get(f"{BACKEND_API_URL}/health", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def get_citation(source: str) -> str:
    """Returns a clear citation badge indicating how the query was resolved."""
    if source == "deterministic_tool":
        return "⚡ **Method:** Direct Verified SQL (Deterministic Benchmark Tool - Zero Hallucination)"
    elif source == "dynamic_sql":
        return "🤖 **Method:** Dynamic Text-to-SQL (Query Formulated by Groq LLM)"
    elif source == "input_validation":
        return "🛡️ **Method:** Blocked by Input Security Guardrail"
    return f"📌 **Method:** {source}"


def query_assistant(question: str) -> dict:
    """Sends natural language question to the FastAPI backend service."""
    try:
        with httpx.Client(timeout=50.0) as client:
            resp = client.post(f"{BACKEND_API_URL}/query", json={"question": question})
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 400:
                detail = resp.json().get("detail", {})
                return {
                    "status": "error",
                    "question": question,
                    "answer": detail.get("answer", "Invalid query."),
                    "supporting_data": [],
                    "columns": [],
                    "sql_executed": None,
                    "execution_source": "input_validation",
                    "error": detail.get("error")
                }
    except Exception as e:
        return {
            "status": "error",
            "question": question,
            "answer": f"Unable to reach backend at {BACKEND_API_URL}. If Render is waking up from idle, please retry in a few seconds.",
            "supporting_data": [],
            "columns": [],
            "sql_executed": None,
            "execution_source": "connection_error",
            "error": str(e)
        }


# ==============================================================================
# Sidebar: Benchmark Question Bank & Live Service Info
# ==============================================================================

with st.sidebar:
    st.header("📊 Sales BI Controls")
    st.markdown("Select from the benchmark questions or enter a custom query.")

    st.subheader("Question Bank")
    question_bank = [
        "What is the total revenue?",
        "Which product generated the highest revenue?",
        "What is the monthly revenue trend?",
        "Which region generated the highest sales?",
        "How did revenue change between January and February?",
        "Which sales channel generated the most revenue?",
        "what is revenue for TXN0034 Keyboard?",
        "List all returned or anomalous transactions.",
        "Compare online and retail revenue."
    ]

    selected_question = st.selectbox(
        "Choose a benchmark query:",
        options=question_bank,
        key="question_bank",
    )
    run_selected = st.button(
        "Run selected question",
        key="run_selected_question",
        use_container_width=True,
    )

    st.markdown("---")
    st.subheader("Data Quality Audit")
    # Clean audit summary of the 51 transactions
    audit_data = [
        {"Status": "VALID", "Transactions": 48, "Gross Revenue": "$1,443,700"},
        {"Status": "STATUS_RETURNED", "Transactions": 1, "Gross Revenue": "$19,000"},
        {"Status": "ZERO_QUANTITY", "Transactions": 1, "Gross Revenue": "$0"},
        {"Status": "MISSING_UNIT_PRICE", "Transactions": 1, "Gross Revenue": "$0"},
    ]
    st.dataframe(pd.DataFrame(audit_data), use_container_width=True, hide_index=True)
    st.caption("Total dataset: 51 transactions (48 completed, 3 quarantined anomalies).")

    st.markdown("---")
    st.subheader("🌐 Service Status")
    if get_service_status():
        st.success("Backend: Online & Ready", icon="🟢")
    else:
        st.info("Backend: Waking up from idle...", icon="⏳")
    st.markdown(f"**Backend API:** [FastAPI Cloud Service]({BACKEND_API_URL})")


# ==============================================================================
# Main Chat Area
# ==============================================================================

st.title(" Sales Business Intelligence Assistant")
st.markdown(
    "Ask natural language questions about your sales data. "
    "All queries are verified against the relational database with deterministic mathematical grounding."
)

# Session state initialization
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Display citation
        if msg.get("execution_source"):
            st.caption(get_citation(msg["execution_source"]))

        # Display supporting table if available
        if msg.get("supporting_data"):
            with st.expander("📋 Supporting Data Table", expanded=False):
                st.dataframe(pd.DataFrame(msg["supporting_data"]), use_container_width=True)

        # Display SQL/Tool inspection
        if msg.get("sql_executed"):
            with st.expander("🛠️ Execution Details & SQL Query", expanded=False):
                st.code(msg["sql_executed"], language="sql")


# Handle input from chat or the question bank
user_input = st.chat_input("Ask a question about sales, products, regions, or trends...")
prompt_to_process = selected_question if run_selected else user_input

if prompt_to_process:
    # 1. Render and record user prompt
    st.session_state.messages.append({"role": "user", "content": prompt_to_process})
    with st.chat_message("user"):
        st.markdown(prompt_to_process)

    # 2. Process query through backend API
    with st.chat_message("assistant"):
        with st.spinner("Analyzing sales database via backend..."):
            result = query_assistant(prompt_to_process)

            answer = result.get("answer", "No response generated.")
            supporting_data = result.get("supporting_data", [])
            sql_executed = result.get("sql_executed")
            source = result.get("execution_source", "unknown")
            status_flag = result.get("status", "error")

            # Render answer
            if status_flag == "error":
                st.error(answer)
            else:
                st.markdown(answer)

            # Render citation
            if source:
                st.caption(get_citation(source))

            # Render supporting data table
            if supporting_data:
                with st.expander("📋 Supporting Data Table", expanded=True):
                    st.dataframe(pd.DataFrame(supporting_data), use_container_width=True)

            # Render SQL query inspectability
            if sql_executed:
                with st.expander("🛠️ Execution Details & SQL Query", expanded=False):
                    st.code(sql_executed, language="sql")

    # 3. Save assistant message to session state
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "supporting_data": supporting_data,
        "sql_executed": sql_executed,
        "execution_source": source
    })
