# Sales BI Assistant

A simple AI-powered Business Intelligence tool that lets you ask questions about sales data in plain English and gets back real numbers from an SQLite database.

Built with Python, SQLite, LangGraph, FastAPI, and Streamlit.

---

## 1. Quick Setup & Run

### Setup
```bash
# 1. Activate your virtual environment
.\venv\Scripts\activate          # Windows PowerShell
# source venv/bin/activate       # Mac/Linux

# 2. Install packages
pip install -r requirements.txt
```

Make sure you have a `.env` file in the project root with your Groq API key:
```ini
GROQ_API_KEY=your_key_here
```

### Running the Project

- **Streamlit Web App (Easiest way to test):**
  ```bash
  streamlit run app.py
  ```
  Open `http://localhost:8501`. You will see quick-click buttons for the 5 challenge questions, a chat box for custom questions, and data tables with SQL details.

- **FastAPI Server:**
  ```bash
  python api.py
  ```
  Runs on `http://localhost:8000`. You can send POST requests to `/query`:
  ```bash
  curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d "{\"question\": \"What is the total revenue?\"}"
  ```

- **Run Tests:**
  ```bash
  pytest -v test_core.py
  ```

---

## 2. How the System Works (Architecture)

```mermaid
flowchart TD
    User["User Question\n(Chat or API)"] --> InputCheck["1. Check Input\n(Empty, Null, Injection guards)"]
    InputCheck --> Router{"2. Is it one of the 5 benchmark questions?"}

    Router -->|Yes| FastTrack["3A. Deterministic Tool\n(Pre-written SQL, 100% accurate)"]
    Router -->|No, custom question| AIQuery["3B. Text-to-SQL with Groq\n(Writes read-only SQL from schema)"]

    AIQuery --> SafetyCheck["4. SQL Safety Check\n(Read-only mode, table whitelist)"]
    SafetyCheck -->|"Syntax Error (retries under 2)"| AIQuery

    FastTrack --> Answer["5. Format Final Answer\n(Summary text + data table + SQL used)"]
    SafetyCheck --> Answer
```

### In Plain English:
1. **Input Check:** Rejects empty queries, whitespace, or obvious injection attempts like `drop table`.
2. **Intent Routing:** If you ask one of the 5 main questions (like *"What is the total revenue?"*), it calls a pre-written, verified SQL function. This guarantees zero AI math hallucination.
3. **Dynamic Text-to-SQL:** If you ask a custom question (like *"Which sales channel is better?"*), the LLM reads the database schema and writes a SQL query.
4. **Execution & Answer:** The query runs on SQLite, and the user gets a plain English answer along with the raw data table.

---

## 3. SQL Safety & Database Protection

To make sure the AI never deletes data or breaks the database, we use **multiple layers of protection**:

1. **Read-Only SQLite Connection (`mode=ro`):**
   When executing queries, the database is opened with URI `mode=ro`:
   ```python
   uri = f"file:///{db_path}?mode=ro"
   conn = sqlite3.connect(uri, uri=True)
   ```
   At the operating system level, write permissions are denied.

2. **PRAGMA query_only = ON:**
   Right after connecting, we run:
   ```python
   conn.execute("PRAGMA query_only = ON;")
   ```
   This tells the SQLite engine itself to immediately block any write, delete, update, or create commands.

3. **Restricted Table Whitelist:**
   The validator checks that queries can ONLY access allowed tables/views:
   - `sales`
   - `v_valid_sales`
   - `v_sales_anomalies`
   Any query trying to access internal tables (like `sqlite_master`) or other tables is blocked before running.

4. **Blocked Keywords:**
   Commands like `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, and `TRUNCATE` are blocked.

5. **No Multi-Statements:**
   Queries with multiple statements separated by semicolons (e.g., `SELECT 1; DROP TABLE sales;`) are rejected.

---

## 4. Questions Supported: Benchmark & Dynamic

### A. The 5 Benchmark Questions (Deterministic)
These 5 questions are calculated directly using clean SQL on `v_valid_sales` (excluding returned orders and broken records):

| # | Question | Answer / Result | Details |
| :---: | :--- | :--- | :--- |
| **Q1** | *What is the total revenue?* | **$1,439,200.00** | Net revenue from 48 completed sales (Gross: $1,443,700, Discounts: $4,500). |
| **Q2** | *Which product generated the highest revenue?* | **Monitor ($473,000.00)** | 50 units sold. (Desk was #2 with $222,500). |
| **Q3** | *What is the monthly revenue trend?* | **6 Months Tracked** | Jan: $210,250 → Feb: $234,600 (+11.58%) → Mar: $223,900 (-4.56%) → Apr: $240,700 (+7.50%) → May: $318,500 (+32.32%) → Jun: $211,250 (-33.67%). |
| **Q4** | *Which region generated the highest sales?* | **South ($411,200.00)** | 13 orders. (North was #2 with $384,450). |
| **Q5** | *How did revenue change between two months?* | **+$24,350.00 (+11.58%)** | Comparing Jan 2026 ($210,250) to Feb 2026 ($234,600). Works for any two months. |

### B. Dynamic Questions (Custom Inquiries)
You can also ask arbitrary questions. The AI writes custom read-only SQL:

- *"Show sales breakdown by sales channel"*  
  $\rightarrow$ Groups by `Sales_channel`. Shows Online generated $746,750 (353 units) and Retail generated $692,450 (280 units).
- *"Which product category had the highest discount?"*  
  $\rightarrow$ Groups by `Category` and sums `Discount_amount`.
- *"List the top 3 biggest orders by quantity"*  
  $\rightarrow$ Returns the top 3 rows ordered by `Quantity DESC`.
- *"Show all bad or returned transactions"*  
  $\rightarrow$ Queries `v_sales_anomalies` to show the 3 flagged records (1 returned, 1 zero quantity, 1 missing price).

---

## 5. Automated Tests (19 Tests Passing)

Run tests anytime with:
```bash
pytest -v test_core.py
```

What the 19 tests check:
- **Core Numbers (Q1 to Q5):** Checks that all calculations match the expected database numbers.
- **Bad Inputs:** Checks that empty strings `""`, whitespace `"   "`, and `None` don't crash the server.
- **SQL Security:** Checks that `DROP TABLE`, `DELETE`, and multi-statement queries are blocked.
- **Engine Security:** Directly tests that `get_readonly_connection()` throws an error if someone tries to delete data.
- **Table Whitelist:** Checks that queries to `sqlite_master` or `users` get blocked.
- **Data Cleanup:** Checks that returned/broken orders are kept separate from valid sales.
- **FastAPI Endpoints:** Checks `/health`, `/schema`, and `/query` (success 200 and error 400).

---

## 6. How I Built This & AI Reflections

### AI Tools I Used
- **GitHub Copilot:** Used in VS Code for code patching, auto-completing function types, and writing repetitive pytest test cases.
- **Groq API (`qwen/qwen3.8-27b`):** The LLM that translates user questions into SQL. Selected because it responds in ~300ms.

### How I Used AI
- I used GitHub Copilot to speed up boilerplate code (like Pydantic models, SQL row dictionaries, and test structures).
- I used LLM prompts to inspect the CSV columns and understand the data.
- In the actual app, I only let the LLM handle understanding English questions. I did NOT let the LLM do math. All math is done by SQL in the database so answers are always 100% accurate.

### Problems I Faced & How I Fixed Them
1. **Old model didn't exist:** I initially tried `llama-3.3-70b-versatile` on Groq, but got a `model_not_found` error. I ran a script to list available models on my key and switched to `qwen/qwen3.8-27b`, which worked right away.
2. **Blank answers with reasoning models:** I tested with `openai/gpt-oss-20b`, but it used up all its tokens on internal thinking steps and returned empty SQL. Switching to Qwen solved this.
3. **Bad data in the CSV:** The raw CSV had 3 problematic rows (TXN0033 was returned, TXN0034 had 0 quantity, and TXN0051 had no price). If you just ran `SUM(price * quantity)`, the totals were wrong. I fixed this by creating `clean.py` and an SQLite view `v_valid_sales` that only includes valid, completed sales.
4. **Streamlit reloading database repeatedly:** At first, `database.init_db()` ran on every click in Streamlit, re-reading the CSV and writing to disk every time. I fixed it by caching the setup with `@st.cache_resource` and adding a check so it skips re-creating the database if it already exists.
5. **Database errors showing as success:** Early on, if the database threw an error on a question, the router returned an empty string but marked the status as success. I wrote a `_format_db_response()` helper that checks `db_res.get("success")` and forwards the real error to the user.

### What I Would Add With One More Day
1. **Interactive Charts:** Show bar charts and trend lines automatically in Streamlit using Altair or Plotly.
2. **Chat Memory:** Allow follow-up questions like *"What about for last month?"* without having to re-type the full question.
3. **Query Caching:** Save answers to common questions in memory so repeated questions answer in 0ms without calling the LLM.
