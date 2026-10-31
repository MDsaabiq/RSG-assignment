# agent.py
"""
LangGraph-Powered AI Business Intelligence Agent.

Architecture:
- StateGraph workflow orchestrating:
  1. Input Validation Node (backend security, null/empty checks, injection prevention)
  2. Intent Routing Node (routes 5 benchmark questions to deterministic tools)
  3. Dynamic SQL Generation Node (LLM Text-to-SQL with Groq + schema injection)
  4. SQL Safety & Execution Node (read-only verification + self-healing retry loop)
  5. Answer Synthesis Node (summarizes database figures into business answers)

FastAPI endpoints are decoupled and located separately in api.py.
"""

import os
import re
from typing import TypedDict, Optional, List, Dict, Any
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END

import database

# Load environment variables
load_dotenv()

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEY2")
DEFAULT_MODEL = "qwen/qwen3.8-27b"
MAX_SQL_RETRIES = 4


# ==============================================================================
# 1. State Definition
# ==============================================================================

class AgentState(TypedDict):
    question: Optional[str]
    cleaned_query: str
    is_valid: bool
    route: str  # "deterministic", "dynamic_sql", "error"
    sql: Optional[str]
    answer: str
    supporting_data: List[Dict[str, Any]]
    columns: List[str]
    execution_source: str
    error: Optional[str]
    retry_count: int


# ==============================================================================
# 2. LLM Client Initialization
# ==============================================================================

def get_groq_client():
    """Initializes and returns Groq client using API key from .env."""
    if not GROQ_API_KEY:
        return None
    try:
        from groq import Groq
        return Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"[Warning] Failed to initialize Groq client: {e}")
        return None


# ==============================================================================
# 3. LangGraph Nodes
# ==============================================================================

def input_validation_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 1: Backend Query Input Validation
    Protects against null, empty strings, whitespace, length overflow,
    and destructive prompt injection attempts.
    """
    raw_query = state.get("question")

    if raw_query is None:
        return {
            "is_valid": False,
            "error": "Query cannot be null.",
            "answer": "Invalid query: Query cannot be null.",
            "execution_source": "input_validation",
            "route": "error"
        }

    trimmed = str(raw_query).strip()

    if len(trimmed) == 0:
        return {
            "is_valid": False,
            "error": "Query cannot be empty or pure whitespace.",
            "answer": "Invalid query: Query cannot be empty or pure whitespace.",
            "execution_source": "input_validation",
            "route": "error"
        }

    if len(trimmed) > 1000:
        return {
            "is_valid": False,
            "error": "Query exceeds maximum allowed length of 1000 characters.",
            "answer": "Invalid query: Query exceeds maximum allowed length of 1000 characters.",
            "execution_source": "input_validation",
            "route": "error"
        }

    # Guard against destructive SQL injection / malicious prompts
    suspicious_patterns = [
        r"\bdrop\s+table\b",
        r"\bdelete\s+from\b",
        r"\btruncate\s+table\b",
        r"\bupdate\s+\w+\s+set\b",
        r"\balter\s+table\b"
    ]
    for pattern in suspicious_patterns:
        if re.search(pattern, trimmed, re.IGNORECASE):
            return {
                "is_valid": False,
                "error": "Destructive SQL operations are not permitted in queries.",
                "answer": "Invalid query: Destructive SQL operations are not permitted in queries.",
                "execution_source": "input_validation",
                "route": "error"
            }

    return {
        "is_valid": True,
        "cleaned_query": trimmed,
        "error": None
    }


def _format_db_response(db_res: Dict[str, Any], default_summary: str) -> Dict[str, Any]:
    """Helper to check database result and propagate errors instead of falsely reporting success."""
    is_ok = db_res.get("success", False)
    return {
        "route": "deterministic",
        "answer": db_res.get("summary_text", default_summary) if is_ok else f"Database error: {db_res.get('error')}",
        "supporting_data": db_res.get("rows", []),
        "columns": db_res.get("columns", []),
        "sql": db_res.get("query"),
        "execution_source": "deterministic_tool",
        "error": None if is_ok else db_res.get("error", "Database query failed")
    }


def intent_router_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 2: Intent Router
    Evaluates if query matches one of the 5 explicit challenge questions.
    If matched, calls deterministic database tools (zero hallucination).
    Otherwise, routes to dynamic SQL generation.
    """
    q = state.get("cleaned_query", "").lower().strip()

    # Challenge Q1: Total revenue
    if (
        ("total" in q and "revenue" in q)
        or ("overall" in q and "revenue" in q)
        or ("how much revenue" in q and "total" in q)
        or q in ["what is the total revenue?", "what is the total revenue"]
    ):
        return _format_db_response(database.get_total_revenue(), "Total revenue calculated.")

    # Challenge Q2: Top product by revenue
    if (
        ("product" in q and ("highest" in q or "top" in q or "best" in q) and "revenue" in q)
        or ("which product generated the highest revenue" in q)
        or ("top product" in q)
    ):
        return _format_db_response(database.get_top_product(limit=3), "Top product identified.")

    # Challenge Q3: Monthly revenue trend
    if (
        ("monthly" in q and ("trend" in q or "revenue" in q or "growth" in q))
        or ("month by month" in q)
        or ("monthly revenue trend" in q)
    ):
        return _format_db_response(database.get_monthly_revenue_trend(), "Monthly revenue trend calculated.")

    # Challenge Q4: Highest sales region
    if (
        ("region" in q and ("highest" in q or "top" in q or "best" in q or "most" in q))
        or ("which region generated the highest sales" in q)
        or ("top region" in q)
    ):
        return _format_db_response(database.get_top_region(limit=4), "Top sales region identified.")

    # Challenge Q5: Revenue change between two months
    if ("between" in q and ("month" in q or "revenue" in q)) or ("change between" in q):
        m1 = "2026-01"
        m2 = "2026-02"
        month_map = {
            "jan": "2026-01", "january": "2026-01",
            "feb": "2026-02", "february": "2026-02",
            "mar": "2026-03", "march": "2026-03",
            "apr": "2026-04", "april": "2026-04",
            "may": "2026-05",
            "jun": "2026-06", "june": "2026-06"
        }
        found_months = []
        for word, m_val in month_map.items():
            if word in q and m_val not in found_months:
                found_months.append(m_val)

        if len(found_months) >= 2:
            m1, m2 = found_months[0], found_months[1]

        return _format_db_response(
            database.compare_monthly_revenue(m1, m2),
            f"Revenue comparison between {m1} and {m2} completed."
        )

    # Route to dynamic SQL generation
    return {
        "route": "dynamic_sql",
        "error": None
    }


def generate_sql_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 3: Dynamic SQL Generation
    Prompts Groq LLM with database schema and user question.
    Incorporates prior error feedback if this is a self-correction retry.
    """
    client = get_groq_client()
    if not client:
        return {
            "sql": None,
            "error": "Groq API key not configured or client initialization failed.",
            "answer": "Unable to generate query: LLM service is unavailable.",
            "execution_source": "dynamic_sql"
        }

    schema_info = database.get_schema_info()
    question = state.get("cleaned_query", "")
    last_error = state.get("error")

    system_prompt = f"""
You are an expert SQLite business intelligence SQL developer.
Generate a single valid read-only SQLite query to answer the user's question.

{schema_info}

STRICT INSTRUCTIONS:
1. Output ONLY the raw SQL query. No explanations, no markdown blocks, no commentary.
2. Query strictly from 'v_valid_sales' unless user asks for anomalies or returned orders.
3. Use 'net_revenue' for revenue calculations.
4. Do not use destructive operations (NO DROP, DELETE, UPDATE, INSERT, ALTER).
"""

    user_content = f"User question: {question}"
    if last_error:
        user_content += f"\n\nYour previous SQL produced this error: {last_error}. Please correct the SQL."

    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": user_content.strip()}
            ],
            temperature=0.0,
            max_tokens=250
        )
        raw_text = response.choices[0].message.content.strip()

        # Clean markdown wrappers
        cleaned_sql = re.sub(r"^```(sql)?", "", raw_text, flags=re.IGNORECASE).strip()
        cleaned_sql = re.sub(r"```$", "", cleaned_sql).strip()

        return {
            "sql": cleaned_sql,
            "error": None
        }
    except Exception as e:
        return {
            "sql": None,
            "error": f"LLM Text-to-SQL generation failed: {str(e)}",
            "answer": f"LLM service error: {str(e)}"
        }


def execute_and_synthesize_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 4: SQL Safety Validation, Execution, & Response Synthesis
    Validates read-only safety, executes query against SQLite,
    and synthesizes a natural language business summary.
    If execution fails, increments retry_count for reflection loop.
    """
    sql = state.get("sql")
    retries = state.get("retry_count", 0)

    if not sql:
        return {
            "error": state.get("error", "No SQL generated to execute."),
            "answer": state.get("answer", "No query could be formulated."),
            "retry_count": retries + 1
        }

    # 1. SQL Safety Validation
    is_safe, safety_err = database.validate_sql(sql)
    if not is_safe:
        return {
            "error": f"Security violation: {safety_err}",
            "answer": f"Query blocked: {safety_err}",
            "retry_count": retries + 1
        }

    # 2. Database Execution
    db_res = database.execute_safe_query(sql)
    if not db_res.get("success", False):
        return {
            "error": db_res.get("error", "Database execution error"),
            "answer": f"Database query failed: {db_res.get('error')}",
            "retry_count": retries + 1
        }

    rows = db_res.get("rows", [])
    columns = db_res.get("columns", [])

    # 3. Answer Synthesis
    client = get_groq_client()
    summary_answer = f"Query executed successfully with {len(rows)} result(s)."

    if not rows:
        # Check if the user asked about a transaction that was flagged as an anomaly
        txn_match = re.search(r"\b(TXN\d+)\b", f"{state.get('cleaned_query')} {sql}", re.IGNORECASE)
        if txn_match:
            txn_id = txn_match.group(1).upper()
            anomaly_check = database.execute_safe_query(
                f"SELECT Transaction_Id, Product, Quantity, Unit_price, Status, data_quality_flag FROM v_sales_anomalies WHERE Transaction_Id = '{txn_id}'"
            )
            if anomaly_check.get("success") and anomaly_check.get("rows"):
                anom = anomaly_check["rows"][0]
                flag = anom.get("data_quality_flag")
                summary_answer = (
                    f"Transaction {txn_id} ({anom.get('Product')}) has no valid revenue because it was flagged as an anomaly ({flag}). "
                    f"Details: Quantity={anom.get('Quantity')}, Unit_price={anom.get('Unit_price')}, Status='{anom.get('Status')}'."
                )
                rows = anomaly_check["rows"]
                columns = anomaly_check.get("columns", [])
        else:
            summary_answer = "No matching records found in valid completed sales."

    elif client and rows:
        synth_prompt = f"""
You are a business intelligence assistant. Summarize the answer to the user's question
based strictly on the database query result below.

Question: {state.get('cleaned_query')}
SQL Query: {sql}
Data: {rows[:10]}

Rules:
- State the key finding clearly and directly.
- Use only the numbers present in the data rows.
- Keep the response within 2-3 sentences.
"""
        try:
            resp = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[{"role": "user", "content": synth_prompt}],
                temperature=0.2,
                max_tokens=150
            )
            summary_answer = resp.choices[0].message.content.strip()
        except Exception:
            pass

    return {
        "answer": summary_answer,
        "supporting_data": rows,
        "columns": columns,
        "execution_source": "dynamic_sql",
        "error": None
    }


# ==============================================================================
# 4. LangGraph Routing Functions
# ==============================================================================

def route_after_validation(state: AgentState) -> str:
    """Routes to intent router if valid, or terminates if input is invalid."""
    return "intent_router" if state.get("is_valid", False) else END


def route_after_intent(state: AgentState) -> str:
    """Routes to generate_sql if dynamic analysis is needed, else terminates with deterministic tool."""
    return "generate_sql" if state.get("route") == "dynamic_sql" else END


def route_after_execution(state: AgentState) -> str:
    """
    Self-correction conditional edge:
    If execution succeeded (error is None), ends.
    If execution failed and retries < MAX_SQL_RETRIES, loops back to generate_sql.
    Otherwise, terminates with error.
    """
    if state.get("error") is None:
        return END

    if state.get("retry_count", 0) < MAX_SQL_RETRIES:
        return "generate_sql"

    return END


# ==============================================================================
# 5. Build & Compile LangGraph
# ==============================================================================

def build_agent_graph():
    """Constructs and compiles the LangGraph StateGraph workflow."""
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("input_validation", input_validation_node)
    workflow.add_node("intent_router", intent_router_node)
    workflow.add_node("generate_sql", generate_sql_node)
    workflow.add_node("execute_and_synthesize", execute_and_synthesize_node)

    # Add Edges & Conditional Routing
    workflow.add_edge(START, "input_validation")
    workflow.add_conditional_edges("input_validation", route_after_validation)
    workflow.add_conditional_edges("intent_router", route_after_intent)
    workflow.add_edge("generate_sql", "execute_and_synthesize")
    workflow.add_conditional_edges("execute_and_synthesize", route_after_execution)

    return workflow.compile()


# Global compiled graph instance
agent_graph = build_agent_graph()


# ==============================================================================
# 6. Public API: Process User Query
# ==============================================================================

def process_user_query(query: Optional[str]) -> Dict[str, Any]:
    """
    Main interface to process natural language questions through the LangGraph agent.
    Returns uniform structured dictionary:
    {
        "status": "success" | "error",
        "question": str,
        "answer": str,
        "supporting_data": list of dicts,
        "columns": list of str,
        "sql_executed": str or None,
        "execution_source": "deterministic_tool" | "dynamic_sql" | "input_validation",
        "error": str or None
    }
    """
    initial_state: AgentState = {
        "question": query,
        "cleaned_query": "",
        "is_valid": False,
        "route": "",
        "sql": None,
        "answer": "",
        "supporting_data": [],
        "columns": [],
        "execution_source": "",
        "error": None,
        "retry_count": 0
    }

    try:
        final_state = agent_graph.invoke(initial_state)

        has_error = final_state.get("error") is not None
        return {
            "status": "error" if has_error else "success",
            "question": str(query) if query is not None else "",
            "answer": final_state.get("answer", ""),
            "supporting_data": final_state.get("supporting_data", []),
            "columns": final_state.get("columns", []),
            "sql_executed": final_state.get("sql"),
            "execution_source": final_state.get("execution_source", "langgraph"),
            "error": final_state.get("error")
        }
    except Exception as e:
        return {
            "status": "error",
            "question": str(query) if query is not None else "",
            "answer": f"Unexpected execution error: {str(e)}",
            "supporting_data": [],
            "columns": [],
            "sql_executed": None,
            "execution_source": "pipeline_exception",
            "error": str(e)
        }


# ==============================================================================
# CLI Verification
# ==============================================================================

if __name__ == "__main__":
    print("=== Testing LangGraph Agent Workflow ===\n")

    test_queries = [
        "What is the total revenue?",
        "Which product generated the highest revenue?",
        "What is the monthly revenue trend?",
        "Which region generated the highest sales?",
        "How did revenue change between January and February?",
        "Show sales breakdown by sales channel",  # Dynamic custom SQL
        "",                                      # Empty edge case
        "DROP TABLE sales;"                      # SQL injection / destructive test
    ]

    for q in test_queries:
        print(f"User Question: '{q}'")
        res = process_user_query(q)
        print(f"  Status: {res['status']} | Source: {res['execution_source']}")
        print(f"  Answer: {res['answer']}")
        if res.get("sql_executed"):
            print(f"  SQL/Tool: {res['sql_executed'].strip()}")
        if res.get("error"):
            print(f"  Error: {res['error']}")
        print("-" * 60)
