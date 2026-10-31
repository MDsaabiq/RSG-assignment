# Mini AI Business Intelligence Assistant
### AI-Assisted Development Challenge for GET Selection

A resilient, deterministic natural language Business Intelligence Assistant that answers sales performance questions backed by verified relational database queries and LangGraph agentic workflow routing.

---

## 1. System Architecture

The application adopts a **Decoupled 3-Tier Architecture** separating data access, agentic workflow orchestration, and client delivery:

```mermaid
flowchart TD
    User["Business User / Evaluator"] --> Streamlit["Streamlit UI (app.py)"]
    User --> FastAPI["REST API (api.py)"]
    
    FastAPI --> Agent["LangGraph Agent (agent.py)"]
    Streamlit --> Agent

    subgraph LangGraphWorkflow["LangGraph State Workflow"]
        direction TB
        Node1["Node 1: Input Validation\n(Empty, Null, SQL Injection Guard)"]
        Node2{"Node 2: Intent Router\n(Benchmark vs Custom)"}
        Node3A["Node 3A: Deterministic Tools\n(Pre-compiled Benchmark Logic)"]
        Node3B["Node 3B: Dynamic Text-to-SQL\n(Groq Qwen 2.5 with Schema Context)"]
        Node4["Node 4: SQL Safety & Execution\n(Read-Only SELECT Validator)"]
        Node5["Node 5: Response Synthesis\n(Cited Data Figures)"]

        Node1 --> Node2
        Node2 -->|Matches Q1-Q5| Node3A
        Node2 -->|Novel Query| Node3B
        Node3B --> Node4
        Node4 -->|Syntax Error (Retries < 2)| Node3B
        Node4 --> Node5
        Node3A --> Node5
    end

    Agent --> LangGraphWorkflow
    Node3A --> DB[(SQLite: sales.db)]
    Node4 --> DB

    subgraph DatabaseLayer["Data Management (database.py)"]
        DB --> ViewValid["View: v_valid_sales\n(48 Completed Records)"]
        DB --> ViewAnomalies["View: v_sales_anomalies\n(3 Flagged Records)"]
    end
```

---

## 2. Key Technical Concepts (Interview Readiness)

### Why "Vectorless RAG"?
* **Traditional Vector RAG Flaw:** Vector databases rely on semantic distance (cosine similarity) across text chunks. If asked *"What is the total revenue?"*, vector search returns arbitrary transaction snippets; it cannot calculate sums, averages, or month-over-month differences, forcing the LLM to hallucinate arithmetic.
* **Vectorless (Structured) RAG:** The assistant retrieves schema metadata, binds natural language intents to deterministic SQL execution over SQLite, and synthesizes answers strictly grounded in actual database results.

### Agentic AI with LangGraph
Instead of a fragile one-shot prompt, the agent is implemented as a state machine (`langgraph.graph.StateGraph`):
1. **Input Validation Node:** Rejects null, empty, whitespace, and prompt injection traps.
2. **Intent Routing Node:** Directs the 5 core challenge questions to deterministic tools for 100% calculation accuracy.
3. **Dynamic SQL Generation Node:** Injects relational schema to translate ad-hoc inquiries into SQLite queries.
4. **Safety & Self-Correction Node:** Enforces read-only execution (`SELECT` only) and feeds database syntax errors back to the model for self-healing (bounded to `max_retries = 2`).

---

## 3. Challenge Benchmark Questions & Verified Results

All 5 assessment questions are verified deterministically against `v_valid_sales`:

| # | Challenge Question | Status | Verified Metric / Result | Supporting Details |
| :---: | :--- | :---: | :--- | :--- |
| **Q1** | *What is the total revenue?* | ✅ Supported | **$1,439,200.00 Net Revenue** | Gross: $1,443,700.00; Discounts: $4,500.00; 48 completed transactions. |
| **Q2** | *Which product generated the highest revenue?* | ✅ Supported | **'Monitor' ($473,000.00)** | 50 units sold across Electronics category (Desk 2nd: $222,500.00). |
| **Q3** | *What is the monthly revenue trend?* | ✅ Supported | **6-Month Trend Analyzed** | Jan: $210,250 → Feb: $234,600 (+11.58%) → Mar: $223,900 (-4.56%) → Apr: $240,700 (+7.50%) → May: $318,500 (+32.32%) → Jun: $211,250 (-33.67%). |
| **Q4** | *Which region generated the highest sales?* | ✅ Supported | **'South' ($411,200.00)** | 13 completed orders (North 2nd: $384,450.00; East 3rd: $346,700.00; West 4th: $296,850.00). |
| **Q5** | *How did revenue change between two months?* | ✅ Supported | **+$24,350.00 (+11.58%)** | Jan 2026 ($210,250.00) vs Feb 2026 ($234,600.00). Supports arbitrary month pairs. |

---

## 4. Data Management & Anomaly Handling

The raw dataset (`ai_bi_assistant_sales_data - GET.csv`) contains 51 transaction records. `clean.py` and `database.py` isolate quality defects to prevent skewed metrics:

* **Clean Completed Records (48 rows):** Assigned `is_valid_sale = 1` and queried via `v_valid_sales`.
* **Flagged Anomalies (3 rows):**
  1. `TXN0033` (Monitor): **Status = 'Returned'** (Revenue excluded to prevent counting refunded orders).
  2. `TXN0034` (Keyboard): **Quantity = 0** (Coerced to 0 revenue; flagged as `ZERO_QUANTITY`).
  3. `TXN0051` (Laptop Stand): **Unit_price = Missing** (Coerced to 0.0; flagged as `MISSING_UNIT_PRICE`).

---

## 5. Security & Sandbox Guardrails

Built specifically to resist evaluation sandbox traps and injection attempts:
* **Zero Unhandled Crashes:** All entry points handle `None`, `""`, whitespace, and malformed strings gracefully, returning structured `{"status": "error", ...}` payloads.
* **SQL Injection & DDL Prevention:** `database.validate_sql` rejects all multi-statement queries (e.g. `SELECT 1; DROP TABLE sales;`) and blocks destructive commands (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`, `EXEC`, `PRAGMA`).
* **Hard Exit Limits:** LangGraph retry edges are bounded (`MAX_SQL_RETRIES = 2`) to prevent infinite recursion.
* **Defensive Dictionary Access:** All state lookups use `.get()` with safe fallback defaults.

---

## 6. Project Structure

```text
├── data/
│   ├── ai_bi_assistant_sales_data - GET.csv   # Raw source transaction data
│   └── cleaned.csv                            # Cleaned and normalized data
├── question/
│   └── AI Assisted Development Challenge.docx # Challenge specifications
├── clean.py         # ETL pipeline: date parsing, anomaly flagging, revenue calculation
├── database.py      # SQLite ingestion, views, safety validator, deterministic tools
├── agent.py         # LangGraph workflow (validation, routing, text-to-SQL, synthesis)
├── api.py           # FastAPI REST API (/query, /health, /schema)
├── app.py           # Streamlit user interface with chat history & query inspection
├── test_core.py     # 16 automated pytest unit and integration tests
├── requirements.txt # Wheel-pinned dependency definitions
├── .env             # API key configurations (GROQ_API_KEY)
└── README.md        # Comprehensive solution & architecture documentation
```

---

## 7. Setup & Execution Instructions

### Prerequisites
* Python 3.10+ (tested on Python 3.13)
* Windows / Linux / macOS

### 1. Environment Setup
```bash
# Clone the repository
git clone <repository-url>
cd Assignment

# Activate virtual environment
.\venv\Scripts\activate          # Windows PowerShell
# source venv/bin/activate       # Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create or verify your `.env` file in the root directory:
```ini
GROQ_API_KEY=your_groq_api_key_here
```

### 3. Run Automated Tests
```bash
pytest -v test_core.py
```
*Expected: 16 passed tests covering benchmarks, edge cases, SQL injection, and API endpoints.*

### 4. Run the REST API Backend
```bash
python api.py
# Or: uvicorn api:app --reload --port 8000
```
* Access Swagger UI documentation: `http://localhost:8000/docs`
* Health check: `http://localhost:8000/health`
* Query endpoint: `POST http://localhost:8000/query` with `{"question": "What is the total revenue?"}`

### 5. Run the Streamlit Interface
```bash
streamlit run app.py
```
* Interactive web interface accessible at `http://localhost:8501`.

---

## 8. AI Tools & Development Reflection Report

### AI Tools Utilized
* **Antigravity AI Assistant:** Used for rapid architectural synthesis, exploratory analysis, code structuring, and automated test authoring.
* **Groq API (`qwen/qwen3.8-27b`):** Selected for sub-second inference latency (~300ms) and structured SQL synthesis.
* **LangGraph:** Deployed for stateful graph workflow routing and self-correction loops.

### Problems Encountered & How They Were Debugged
1. **Model Deprecation / Not Found Error:**
   * *Issue:* The legacy `llama-3.3-70b-versatile` endpoint returned a `model_not_found` error from Groq.
   * *Resolution:* Dynamically queried Groq's `client.models.list()`, identified active models (`qwen/qwen3.8-27b`), and benchmarked response quality.
2. **Reasoning Token Exhaustion:**
   * *Issue:* Test queries with reasoning-focused models (`openai/gpt-oss-20b`) exhausted token limits within internal reasoning chains, returning blank completion strings.
   * *Resolution:* Switched to `qwen/qwen3.8-27b` with temperature 0.0, which outputs direct, high-accuracy SQL without consuming tokens in reasoning loops.
3. **Data Quality Skew on Aggregates:**
   * *Issue:* Computing raw `SUM(Unit_price * Quantity)` distorted sales figures due to returned transactions (`TXN0033`) and missing unit prices (`TXN0051`).
   * *Resolution:* Implemented `v_valid_sales` view in SQLite to isolate valid completed orders from anomalies.

### What Would Be Improved With Another Day of Work
1. **Interactive Visualization Generation:** Integrate automatic Altair or Plotly chart generation inside `app.py` for monthly revenue and category comparisons.
2. **Semantic Cache:** Implement an SQLite query cache (hashing normalized natural language questions) to achieve instant 0ms responses for recurring user queries.
3. **Multi-Turn Context:** Extend LangGraph state to track conversation thread memory across multi-turn follow-up questions (e.g., *"What about in the East region?"* following a product query).

