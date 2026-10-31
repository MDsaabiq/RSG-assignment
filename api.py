# api.py
"""
FastAPI Backend Service for AI Sales BI Assistant.

Fulfills Assessment Requirement #2:
"Build an API that accepts a user’s question.
Process the question and return a structured answer.
Handle invalid requests and errors."

Run with:
    uvicorn api:app --reload --port 8000
Or:
    python api.py
"""

from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import process_user_query
import database

# Initialize FastAPI application
app = FastAPI(
    title="Sales BI Assistant API",
    description="Natural language business intelligence assistant powered by LangGraph, SQLite, and Groq.",
    version="1.0.0"
)

# Enable CORS for frontend integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# Pydantic Request & Response Schemas
# ==============================================================================

class QueryRequest(BaseModel):
    question: Optional[str] = Field(
        default=None,
        description="Natural language sales or business intelligence question."
    )
    model_config = {
        "json_schema_extra": {
            "example": {
                "question": "What is the total revenue?"
            }
        }
    }


class QueryResponse(BaseModel):
    status: str = Field(description="'success' or 'error'")
    question: str = Field(description="The original user question")
    answer: str = Field(description="Natural language summary of findings")
    supporting_data: List[Dict[str, Any]] = Field(default=[], description="Structured tabular data rows")
    columns: List[str] = Field(default=[], description="Column names for supporting data")
    sql_executed: Optional[str] = Field(default=None, description="SQL query or deterministic tool executed")
    execution_source: str = Field(description="Source of execution: deterministic_tool | dynamic_sql | input_validation")
    error: Optional[str] = Field(default=None, description="Error message if execution failed")


# ==============================================================================
# API Routes
# ==============================================================================

@app.get("/health", status_code=status.HTTP_200_OK, tags=["System"])
def health_check() -> Dict[str, Any]:
    """Health check endpoint to verify API and database readiness."""
    db_res = database.get_total_revenue()
    db_ready = db_res.get("success", False)
    return {
        "status": "healthy" if db_ready else "degraded",
        "service": "Sales BI Assistant API",
        "database_connected": db_ready
    }


@app.get("/schema", status_code=status.HTTP_200_OK, tags=["Metadata"])
def get_database_schema() -> Dict[str, str]:
    """Returns database schema information and column definitions."""
    return {"schema": database.get_schema_info()}


@app.post("/query", response_model=QueryResponse, tags=["Analytics"])
def query_endpoint(payload: QueryRequest) -> QueryResponse:
    """
    Accepts a natural language question, passes it through the LangGraph agent,
    and returns a structured response with answer, supporting figures, and query metadata.
    """
    result = process_user_query(payload.question)

    # If input validation failed, return HTTP 400 Bad Request
    if result.get("execution_source") == "input_validation":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "error",
                "question": result.get("question", ""),
                "error": result.get("error"),
                "answer": result.get("answer")
            }
        )

    return QueryResponse(
        status=result.get("status", "error"),
        question=result.get("question", ""),
        answer=result.get("answer", ""),
        supporting_data=result.get("supporting_data", []),
        columns=result.get("columns", []),
        sql_executed=result.get("sql_executed"),
        execution_source=result.get("execution_source", "unknown"),
        error=result.get("error")
    )


if __name__ == "__main__":
    import uvicorn
    print("Starting FastAPI server on http://localhost:8000 ...")
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
