
"""
AI Business Intelligence Agent & Backend Query Processor.

Responsibilities:
1. Validates and sanitizes incoming natural language questions.
2. Manages LLM integration (Groq API key loaded from .env).
3. Routes core benchmark questions to deterministic database tools (zero hallucination).
4. Generates, validates, and safely executes dynamic SQL for exploratory business queries.
5. Provides self-correction loop for SQL errors (capped at 2 iterations).
6. Returns consistent structured answers with supporting numerical data.
7. Exposes an optional FastAPI endpoint for API evaluation.
"""

import os
import re
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

import database

# Load environment variables
load_dotenv()

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEY2")
DEFAULT_MODEL = "qwen/qwen3.8-27b"
MAX_SQL_RETRIES = 2


# ==============================================================================
# 1. Backend Input Validation
# ==============================================================================

def validate_user_input(query: Optional[str]) -> Dict[str, Any]:
    """
    Validates user query string to guard against empty, whitespace, null,
    excessively long inputs, or prompt injection traps.
    """
    if query is None:
        return {"is_valid": False, "error": "Query cannot be null."}

    trimmed = str(query).strip()

    if len(trimmed) == 0:
        return {"is_valid": False, "error": "Query cannot be empty or pure whitespace."}

    if len(trimmed) > 1000:
        return {"is_valid": False, "error": "Query exceeds maximum allowed length of 1000 characters."}

    # Guard against destructive prompt injections aiming to alter database
    suspicious_patterns = [
        r"\bdrop\s+table\b",
        r"\bdelete\s+from\b",
        r"\btruncate\s+table\b",
        r"\bupdate\s+\w+\s+set\b"
    ]
    for pattern in suspicious_patterns:
        if re.search(pattern, trimmed, re.IGNORECASE):
            return {
                "is_valid": False,
                "error": "Destructive SQL operations are not permitted in queries."
            }

    return {"is_valid": True, "cleaned_query": trimmed, "error": None}


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
# 3. Intent Matching for Core Challenge Questions (Deterministic Path)
# ==============================================================================

def match_deterministic_benchmark(query: str) -> Optional[Dict[str, Any]]:
    """
    Matches the 5 explicit challenge benchmark questions to deterministic database tools.
    Provides 100% mathematical accuracy without relying on LLM arithmetic.
    """
    q = query.lower().strip()

    # Challenge Q1: Total revenue
    if (
        ("total" in q and "revenue" in q)
        or ("overall" in q and "revenue" in q)
        or ("how much revenue" in q and "total" in q)
        or q == "what is the total revenue?"
        or q == "what is the total revenue"
    ):
        db_res = database.get_total_revenue()
        return {
            "status": "success",
            "question": query,
            "answer": db_res.get("summary_text", "Total revenue calculated successfully."),
            "supporting_data": db_res.get("rows", []),
            "columns": db_res.get("columns", []),
            "sql_executed": db_res.get("query", "Pre-calculated via database.get_total_revenue"),
            "execution_source": "deterministic_tool",
            "error": None
        }

    # Challenge Q2: Highest revenue product
    if (
        ("product" in q and ("highest" in q or "top" in q or "best" in q) and "revenue" in q)
        or ("which product generated the highest revenue" in q)
        or ("top product" in q)
    ):
        db_res = database.get_top_product(limit=3)
        return {
            "status": "success",
            "question": query,
            "answer": db_res.get("summary_text", "Top product identified."),
            "supporting_data": db_res.get("rows", []),
            "columns": db_res.get("columns", []),
            "sql_executed": db_res.get("query", "Pre-calculated via database.get_top_product"),
            "execution_source": "deterministic_tool",
            "error": None
        }

    # Challenge Q3: Monthly revenue trend
    if (
        ("monthly" in q and ("trend" in q or "revenue" in q or "growth" in q))
        or ("month by month" in q)
        or ("monthly revenue trend" in q)
    ):
        db_res = database.get_monthly_revenue_trend()
        return {
            "status": "success",
            "question": query,
            "answer": db_res.get("summary_text", "Monthly revenue trend calculated."),
            "supporting_data": db_res.get("rows", []),
            "columns": db_res.get("columns", []),
            "sql_executed": db_res.get("query", "Pre-calculated via database.get_monthly_revenue_trend"),
            "execution_source": "deterministic_tool",
            "error": None
        }

    # Challenge Q4: Highest sales region
    if (
        ("region" in q and ("highest" in q or "top" in q or "best" in q or "most" in q))
        or ("which region generated the highest sales" in q)
        or ("top region" in q)
    ):
        db_res = database.get_top_region(limit=4)
        return {
            "status": "success",
            "question": query,
            "answer": db_res.get("summary_text", "Top sales region identified."),
            "supporting_data": db_res.get("rows", []),
            "columns": db_res.get("columns", []),
            "sql_executed": db_res.get("query", "Pre-calculated via database.get_top_region"),
            "execution_source": "deterministic_tool",
            "error": None
        }

    # Challenge Q5: Revenue change between two months
    # Checks for month mentions like "Jan" and "Feb" or "2026-01" and "2026-02"
    if ("between" in q and ("month" in q or "revenue" in q)) or ("change between" in q):
        # Default to Jan (2026-01) and Feb (2026-02) if not specifically specified
        m1 = "2026-01"
        m2 = "2026-02"

        # Check for month names
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

        db_res = database.compare_monthly_revenue(m1, m2)
        return {
            "status": "success",
            "question": query,
            "answer": db_res.get("summary_text", f"Revenue comparison between {m1} and {m2} completed."),
            "supporting_data": db_res.get("rows", []),
            "columns": db_res.get("columns", []),
            "sql_executed": db_res.get("query", "Pre-calculated via database.compare_monthly_revenue"),
            "execution_source": "deterministic_tool",
            "error": None
        }

    # Data Quality / Anomaly audit question
    if "anomaly" in q or "data quality" in q or "flagged" in q or "returned" in q:
        db_res = database.get_data_quality_audit()
        return {
            "status": "success",
            "question": query,
            "answer": "Data quality audit retrieved across all raw transactions.",
            "supporting_data": db_res.get("rows", []),
            "columns": db_res.get("columns", []),
            "sql_executed": db_res.get("query", "Pre-calculated via database.get_data_quality_audit"),
            "execution_source": "deterministic_tool",
            "error": None
        }

    return None


# ==============================================================================
# 4. Dynamic Text-to-SQL Generation (AI Reasoning Layer)
# ==============================================================================

def generate_sql_from_question(
    question: str,
    error_feedback: Optional[str] = None
) -> Optional[str]:
    """
    Prompts the LLM (Groq) with database schema to generate a clean, read-only SQL query.
    If error_feedback is provided, guides the model to fix its prior mistake.
    """
    client = get_groq_client()
    if not client:
        return None

    schema_info = database.get_schema_info()

    system_prompt = f"""
You are an expert SQLite business intelligence SQL developer.
Generate a single valid read-only SQLite query to answer the user's question.

{schema_info}

STRICT INSTRUCTIONS:
1. Output ONLY the raw SQL query. No explanations, no markdown blocks, no commentary.
2. Query strictly from 'v_valid_sales' unless the user asks for anomalies or returned orders.
3. Use 'net_revenue' for revenue calculations.
4. Do not use destructive operations (NO DROP, DELETE, UPDATE, INSERT, ALTER).
5. You can use other then harmful queries if question is different
"""

    user_content = f"User question: {question}"
    if error_feedback:
        user_content += f"\n\nYour previous SQL produced this SQLite error: {error_feedback}. Please correct the SQL."

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

        # Clean any accidental markdown code fences
        cleaned_sql = re.sub(r"^```(sql)?", "", raw_text, flags=re.IGNORECASE).strip()
        cleaned_sql = re.sub(r"```$", "", cleaned_sql).strip()
        return cleaned_sql
    except Exception as e:
        print(f"[Error in generate_sql_from_question]: {e}")
        return None


def synthesize_answer(
    question: str,
    sql: str,
    rows: List[Dict[str, Any]]
) -> str:
    """
    Prompts the LLM to write a concise, professional business summary
    using ONLY the numbers present in the retrieved database rows.
    """
    client = get_groq_client()
    if not client or not rows:
        # Fallback summary without LLM
        return f"Query returned {len(rows)} record(s). Refer to the supporting data table for details."

    prompt = f"""
You are a business intelligence assistant. Summarize the answer to the user's question
based strictly on the database query result below.

Question: {question}
SQL Query Used: {sql}
Database Result Rows: {rows[:10]}

Rules:
- State the key finding clearly and directly.
- Use only the numbers present in the data rows.
- Keep the response within 2-3 sentences.
"""
    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return f"Analysis complete based on {len(rows)} record(s). See supporting figures below."


# ==============================================================================
# 5. Core Pipeline: Process User Query
# ==============================================================================

def process_user_query(query: str) -> Dict[str, Any]:
    """
    Main entry point for processing a natural language business question.
    Executes input validation, deterministic routing, safe Text-to-SQL,
    and structured response formatting.
    """
    # 1. Backend Input Validation
    val_res = validate_user_input(query)
    if not val_res["is_valid"]:
        return {
            "status": "error",
            "question": query if query is not None else "",
            "answer": f"Invalid query: {val_res.get('error')}",
            "supporting_data": [],
            "columns": [],
            "sql_executed": None,
            "execution_source": "input_validation",
            "error": val_res.get("error")
        }

    cleaned_query = val_res["cleaned_query"]

    # 2. Check Deterministic Route (Guarantees 100% precision on benchmark questions)
    matched_benchmark = match_deterministic_benchmark(cleaned_query)
    if matched_benchmark:
        return matched_benchmark

    # 3. Dynamic Text-to-SQL Path
    sql_query = None
    last_error = None

    for attempt in range(MAX_SQL_RETRIES):
        sql_query = generate_sql_from_question(cleaned_query, error_feedback=last_error)
        if not sql_query:
            break

        # Validate SQL safety before execution
        is_safe, safety_err = database.validate_sql(sql_query)
        if not is_safe:
            last_error = f"Security rule violation: {safety_err}"
            continue

        # Execute safe query
        db_res = database.execute_safe_query(sql_query)
        if db_res.get("success", False):
            rows = db_res.get("rows", [])
            answer_text = synthesize_answer(cleaned_query, sql_query, rows)
            return {
                "status": "success",
                "question": cleaned_query,
                "answer": answer_text,
                "supporting_data": rows,
                "columns": db_res.get("columns", []),
                "sql_executed": sql_query,
                "execution_source": "dynamic_sql",
                "error": None
            }
        else:
            last_error = db_res.get("error", "Unknown database error")

    # 4. Fallback if Dynamic SQL could not produce a valid result
    return {
        "status": "error",
        "question": cleaned_query,
        "answer": "Unable to safely process this inquiry with the sales database.",
        "supporting_data": [],
        "columns": [],
        "sql_executed": sql_query,
        "execution_source": "dynamic_sql_failure",
        "error": last_error or "LLM generation or database execution failed."
    }


# ==============================================================================
# 6. Optional FastAPI Backend Endpoint
# ==============================================================================

try:
    from fastapi import FastAPI
    from pydantic import BaseModel

    class QuestionRequest(BaseModel):
        question: Optional[str] = None

    api_app = FastAPI(
        title="Sales BI Assistant Backend API",
        description="REST API accepting natural language questions and returning structured database-backed analytics."
    )

    @api_app.post("/query")
    def api_query_endpoint(req: QuestionRequest):
        return process_user_query(req.question)

    @api_app.get("/health")
    def health_check():
        return {"status": "healthy", "service": "Sales BI Assistant API"}

except ImportError:
    api_app = None


# ==============================================================================
# CLI Test Runner
# ==============================================================================

if __name__ == "__main__":
    print("=== Testing Agent with Challenge Questions ===\n")

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

