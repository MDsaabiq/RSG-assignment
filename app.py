# app.py
"""
Streamlit Web Interface for AI Sales BI Assistant.

Fulfills Assessment Requirement #5:
- Clean, responsive interface to enter business questions and view results.
- Displays natural language answers, supporting tabular figures, and SQL query inspectability.
- Pre-loaded quick-prompt buttons for the 5 assessment benchmark questions.
"""

import streamlit as st
import pandas as pd
from agent import process_user_query
import database

st.set_page_config(
    page_title="Sales BI Assistant",
    page_icon="📊",
    layout="wide"
)

# Initialize database if needed
database.init_db()

# ==============================================================================
# Sidebar: Benchmark Controls & Database Audit
# ==============================================================================

with st.sidebar:
    st.header("📊 Sales BI Controls")
    st.markdown("Use quick benchmark questions or enter custom queries below.")

    st.subheader("Challenge Benchmarks:")
    benchmark_questions = [
        "What is the total revenue?",
        "Which product generated the highest revenue?",
        "What is the monthly revenue trend?",
        "Which region generated the highest sales?",
        "How did revenue change between January and February?"
    ]

    clicked_prompt = None
    for idx, q_text in enumerate(benchmark_questions, 1):
        if st.button(f"Q{idx}: {q_text}", key=f"bench_{idx}", use_container_width=True):
            clicked_prompt = q_text

    st.markdown("---")
    st.subheader("Data Quality Summary")
    audit_res = database.get_data_quality_audit()
    if audit_res.get("success", False) and audit_res.get("rows"):
        audit_df = pd.DataFrame(audit_res["rows"])
        st.dataframe(audit_df, use_container_width=True, hide_index=True)
    st.caption("Cleaned dataset: 48 valid transactions, 3 flagged records.")


# ==============================================================================
# Main Chat Area
# ==============================================================================

st.title("🤖 Sales Business Intelligence Assistant")
st.markdown(
    "Ask natural language questions about your sales data. "
    "All answers are deterministically computed and verified against the relational database."
)

# Session state initialization
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Display supporting table if available
        if msg.get("supporting_data"):
            with st.expander("📋 Supporting Data Table", expanded=False):
                st.dataframe(pd.DataFrame(msg["supporting_data"]), use_container_width=True)

        # Display SQL/Tool inspection
        if msg.get("sql_executed"):
            with st.expander("🛠️ Execution Details & SQL Query", expanded=False):
                st.code(msg["sql_executed"], language="sql")
                if msg.get("execution_source"):
                    st.caption(f"Execution Source: `{msg['execution_source']}`")


# Handle input from chat or sidebar quick buttons
user_input = st.chat_input("Ask a question about sales, products, regions, or trends...")
prompt_to_process = clicked_prompt if clicked_prompt else user_input

if prompt_to_process:
    # 1. Render and record user prompt
    st.session_state.messages.append({"role": "user", "content": prompt_to_process})
    with st.chat_message("user"):
        st.markdown(prompt_to_process)

    # 2. Process query through LangGraph Agent
    with st.chat_message("assistant"):
        with st.spinner("Analyzing sales database..."):
            result = process_user_query(prompt_to_process)

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

            # Render supporting data
            if supporting_data:
                with st.expander("📋 Supporting Data Table", expanded=True):
                    st.dataframe(pd.DataFrame(supporting_data), use_container_width=True)

            # Render SQL query inspectability
            if sql_executed:
                with st.expander("🛠️ Execution Details & SQL Query", expanded=False):
                    st.code(sql_executed, language="sql")
                    st.caption(f"Execution Source: `{source}`")

    # 3. Save assistant message to session state
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "supporting_data": supporting_data,
        "sql_executed": sql_executed,
        "execution_source": source
    })

