"""High-value API and database tests for the Sales BI Assistant."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import database
from api import app


database.init_db()
client = TestClient(app)


def successful_query(question):
    response = client.post("/query", json={"question": question})
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "success"
    assert body["question"] == question
    assert body["answer"]
    assert body["supporting_data"]
    assert body["sql_executed"]
    assert body["error"] is None
    return body


def test_all_benchmark_questions_work_through_query_api():
    """The five required business questions work through the public endpoint."""
    cases = [
        ("What is the total revenue?", "1,439,200"),
        ("Which product generated the highest revenue?", "Monitor"),
        ("What is the monthly revenue trend?", "Monthly revenue"),
        ("Which region generated the highest sales?", "South"),
        ("How did revenue change between January and February?", "24,350"),
    ]

    for question, expected_text in cases:
        body = successful_query(question)
        assert expected_text.lower() in body["answer"].lower()
        assert body["execution_source"] == "deterministic_tool"


def test_total_revenue_response_contains_verified_figures():
    """The API returns the database figures supporting the total."""
    body = successful_query("What is the total revenue?")
    row = body["supporting_data"][0]

    assert row["total_net_revenue"] == 1439200.0
    assert row["total_transactions"] == 48
    assert "total_net_revenue" in body["columns"]


def test_custom_question_uses_dynamic_sql_and_returns_real_data():
    """A non-benchmark question uses the dynamic SQL path."""
    sql = (
        "SELECT Sales_channel, ROUND(SUM(net_revenue), 2) AS total_revenue "
        "FROM v_valid_sales GROUP BY Sales_channel ORDER BY total_revenue DESC;"
    )
    fake_client = FakeGroqClient(
        sql,
        "Online generated the most revenue.",
    )

    with patch("agent.get_groq_client", return_value=fake_client):
        body = successful_query("Which sales channel generated the most revenue?")

    assert body["execution_source"] == "dynamic_sql"
    assert body["supporting_data"][0] == {
        "Sales_channel": "Online",
        "total_revenue": 746750.0,
    }


def test_invalid_questions_return_http_400():
    """Invalid public requests are rejected before normal processing."""
    invalid_payloads = [
        {"question": ""},
        {"question": "   "},
        {"question": None},
        {},
    ]

    for payload in invalid_payloads:
        response = client.post("/query", json=payload)
        assert response.status_code == 400
        assert response.json()["detail"]["status"] == "error"


def test_destructive_question_is_rejected_and_data_survives():
    """A destructive prompt cannot modify the database."""
    blocked = client.post("/query", json={"question": "DROP TABLE sales;"})
    assert blocked.status_code == 400

    still_works = successful_query("What is the total revenue?")
    assert "1,439,200" in still_works["answer"]


def test_query_response_contract_is_stable():
    """Successful responses contain the fields API clients depend on."""
    body = successful_query("Which region generated the highest sales?")

    assert set(body) == {
        "status",
        "question",
        "answer",
        "supporting_data",
        "columns",
        "sql_executed",
        "execution_source",
        "error",
    }
    assert isinstance(body["supporting_data"], list)
    assert isinstance(body["columns"], list)


def test_health_endpoint_confirms_database_readiness():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["database_connected"] is True


def test_schema_endpoint_exposes_application_views():
    response = client.get("/schema")

    assert response.status_code == 200
    schema = response.json()["schema"]
    assert "v_valid_sales" in schema
    assert "v_sales_anomalies" in schema


def test_data_quality_audit_separates_invalid_records():
    """Returned and malformed rows remain auditable but separate from valid sales."""
    audit = database.get_data_quality_audit()

    assert audit["success"] is True
    flags = [row["data_quality_flag"] for row in audit["rows"]]
    assert "VALID" in flags
    assert any("RETURNED" in flag for flag in flags)
    assert any("QUANTITY" in flag for flag in flags)
    assert any("PRICE" in flag for flag in flags)


def test_sql_validator_and_readonly_connection_block_writes():
    """Both the SQL guard and SQLite connection reject write attempts."""
    is_valid, error = database.validate_sql(
        "SELECT * FROM sales; DROP TABLE sales;"
    )
    assert is_valid is False
    assert "multi-statement" in error.lower()

    with database.get_readonly_connection() as connection:
        with pytest.raises(database.sqlite3.OperationalError):
            connection.execute("DELETE FROM sales")


class FakeGroqClient:
    """Small Groq-compatible fake used to test dynamic SQL without a network call."""

    def __init__(self, sql, summary):
        self.responses = [sql, summary]
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self.create)
        )

    def create(self, **_kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.responses.pop(0))
                )
            ]
        )
