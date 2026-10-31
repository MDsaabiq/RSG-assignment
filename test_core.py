# test_core.py
"""
Automated Test Suite for Sales BI Assistant.

Covers all 6 assessment criteria:
1. Valid benchmark question 1: Total Revenue computation
2. Valid benchmark question 2: Highest Revenue Product
3. Valid benchmark question 3: Monthly Revenue Trend
4. Valid benchmark question 4: Top Sales Region
5. Valid benchmark question 5: Month-over-Month Revenue Comparison
6. Edge case: Empty string input handling
7. Edge case: Pure whitespace input handling
8. Edge case: Null (None) input handling
9. Security & Sandbox: SQL injection / destructive command prevention
10. Security & Sandbox: Multi-statement attack prevention
11. Data Ingestion & Quality: Valid vs anomalous record segregation
12. Backend API: FastAPI endpoints (/health, /benchmark, /query)
"""

import pytest
from fastapi.testclient import TestClient

import database
from agent import process_user_query
from api import app

# Ensure database is initialized before running tests
database.init_db()
api_client = TestClient(app)


# ==============================================================================
# 1. Benchmark Analytics Tests (Challenge Questions 1-5)
# ==============================================================================

def test_q1_total_revenue_calculation():
    """Q1: What is the total revenue?"""
    res = process_user_query("What is the total revenue?")
    assert res.get("status") == "success"
    assert res.get("execution_source") == "deterministic_tool"
    assert "1,439,200" in res.get("answer", "")
    assert len(res.get("supporting_data", [])) > 0
    row = res["supporting_data"][0]
    assert row.get("total_net_revenue") == 1439200.0
    assert row.get("total_transactions") == 48


def test_q2_top_product_calculation():
    """Q2: Which product generated the highest revenue?"""
    res = process_user_query("Which product generated the highest revenue?")
    assert res.get("status") == "success"
    assert "Monitor" in res.get("answer", "")
    assert len(res.get("supporting_data", [])) > 0
    top_row = res["supporting_data"][0]
    assert top_row.get("Product") == "Monitor"
    assert top_row.get("total_revenue") == 473000.0


def test_q3_monthly_revenue_trend():
    """Q3: What is the monthly revenue trend?"""
    res = process_user_query("What is the monthly revenue trend?")
    assert res.get("status") == "success"
    rows = res.get("supporting_data", [])
    assert len(rows) == 6  # 6 months (2026-01 to 2026-06)
    assert rows[0].get("order_month") == "2026-01"
    assert rows[-1].get("order_month") == "2026-06"
    assert "mom_growth_percent" in rows[1]


def test_q4_top_region():
    """Q4: Which region generated the highest sales?"""
    res = process_user_query("Which region generated the highest sales?")
    assert res.get("status") == "success"
    assert "South" in res.get("answer", "")
    top_row = res["supporting_data"][0]
    assert top_row.get("Region") == "South"
    assert top_row.get("total_revenue") == 411200.0


def test_q5_month_comparison():
    """Q5: How did revenue change between January and February?"""
    res = process_user_query("How did revenue change between January and February?")
    assert res.get("status") == "success"
    assert "24,350" in res.get("answer", "")
    assert "11.58%" in res.get("answer", "")


# ==============================================================================
# 2. Defensive Edge Case Handling (Sandbox Traps)
# ==============================================================================

def test_empty_string_input():
    """Ensures empty string does not crash and returns structured error."""
    res = process_user_query("")
    assert res.get("status") == "error"
    assert res.get("execution_source") == "input_validation"
    assert "empty" in res.get("error", "").lower()


def test_whitespace_input():
    """Ensures whitespace-only string returns structured error."""
    res = process_user_query("     \n\t  ")
    assert res.get("status") == "error"
    assert res.get("execution_source") == "input_validation"
    assert "whitespace" in res.get("error", "").lower()


def test_none_input():
    """Ensures None input does not throw TypeError."""
    res = process_user_query(None)
    assert res.get("status") == "error"
    assert res.get("execution_source") == "input_validation"
    assert "null" in res.get("error", "").lower()


# ==============================================================================
# 3. Security & SQL Safety Guardrails
# ==============================================================================

def test_sql_injection_rejection():
    """Rejects destructive statements like DROP TABLE."""
    res = process_user_query("DROP TABLE sales;")
    assert res.get("status") == "error"
    # Ensure sales table still exists and queryable
    audit = database.get_total_revenue()
    assert audit.get("success") is True


def test_multi_statement_sql_prevention():
    """Direct database validator blocks multi-statement attacks."""
    is_valid, err = database.validate_sql("SELECT * FROM sales; DROP TABLE sales;")
    assert is_valid is False
    assert "multi-statement" in err.lower()


def test_prohibited_keywords():
    """Direct database validator blocks ALTER, DELETE, UPDATE."""
    for kw in ["DELETE FROM sales", "UPDATE sales SET Quantity = 0", "ALTER TABLE sales ADD col INT"]:
        is_valid, err = database.validate_sql(kw)
        assert is_valid is False


# ==============================================================================
# 4. Data Management & Anomaly Segregation
# ==============================================================================

def test_data_quality_isolation():
    """Verifies that returned/invalid transactions are segregated from valid sales."""
    audit = database.get_data_quality_audit()
    assert audit.get("success") is True
    rows = audit.get("rows", [])
    flags = [r.get("data_quality_flag") for r in rows]
    assert "VALID" in flags
    assert any("RETURNED" in f for f in flags)
    assert any("QUANTITY" in f for f in flags)
    assert any("PRICE" in f for f in flags)


# ==============================================================================
# 5. Backend REST API Tests
# ==============================================================================

def test_api_health_endpoint():
    """Verifies GET /health endpoint."""
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "healthy"
    assert data.get("database_connected") is True


def test_api_schema_endpoint():
    """Verifies GET /schema endpoint."""
    response = api_client.get("/schema")
    assert response.status_code == 200
    data = response.json()
    assert "schema" in data
    assert "v_valid_sales" in data["schema"]


def test_api_post_query_success():
    """Verifies POST /query with valid prompt."""
    payload = {"question": "What is the total revenue?"}
    response = api_client.post("/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "success"
    assert "1,439,200" in data.get("answer")


def test_api_post_query_bad_request():
    """Verifies POST /query with empty input returns HTTP 400."""
    payload = {"question": ""}
    response = api_client.post("/query", json=payload)
    assert response.status_code == 400
