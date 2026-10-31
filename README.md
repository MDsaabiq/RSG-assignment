# Sales BI Assistant

A simple AI-powered Business Intelligence tool that lets you ask questions about sales data in plain English and gets back real numbers from an SQLite database.

Built with Python, SQLite, LangGraph, FastAPI, and Streamlit.

---

## 1. Quick Setup & Run

### Try the deployed API first

You can test the deployed FastAPI service without installing the project or
configuring a local Groq API key:

**[Open the live Swagger UI](https://rsg-assignment.onrender.com/docs)**

In Swagger UI:

1. Expand **POST `/query`**.
2. Select **Try it out**.
3. Enter this request body:

   ```json
   {
     "question": "What is the total revenue?"
   }
   ```

4. Select **Execute** to view the structured answer, supporting data, and
   execution details.

You can also test the other benchmark questions or enter a custom sales
question. The deployed service already has its `GROQ_API_KEY` configured.

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

### Quick Test Queries for Dynamic LLM Testing
Once the server or app is running, you can test open-ended questions to evaluate the dynamic Text-to-SQL integration:

- **Data Quality & Anomaly Inspection:**
  ```json
  {
    "question": "List all returned or anomalous transactions."
  }
  ```
  *Result:* The agent queries `v_sales_anomalies` and returns the 3 flagged records (1 returned, 1 zero quantity, 1 missing price) with reasons.

- **Sales Channel Performance:**
  ```json
  {
    "question": "Compare online and retail revenue."
  }
  ```
  *Result:* The agent generates a `GROUP BY Sales_channel` query showing Online ($746,750 / 353 units) vs Retail ($692,450 / 280 units).

---

## 2. How the System Works (Architecture)

```mermaid


%%{init: {
  "theme": "base",
  "themeVariables": {
    "fontFamily": "Arial",
    "fontSize": "14px",
    "lineColor": "#CBD5E1",
    "textColor": "#E5E7EB",
    "edgeLabelBackground": "#073371ff"
  },
  "flowchart": {
    "nodeSpacing": 40,
    "rankSpacing": 40,
    "curve": "basis"
  }
}}%%

flowchart TD
    A["User Question<br/>Streamlit / FastAPI"]
    B["1. Input Validation<br/>Clean query"]
    C{"Routing"}

    D["2A. Deterministic<br/>Verified SQL"]
    E["2B. AI Path<br/>Groq Text-to-SQL"]

    F["3. SQL Safety<br/>Read-only checks"]
    G["4. SQLite<br/>Execute query"]
    H["5. Final Answer<br/>Summary + data"]

    A --> B
    B --> C
    C -->|Yes| D
    C -->|No| E
    D --> F
    E --> F
    F --> G
    G --> H

    classDef start fill:#DBEAFE,stroke:#2563EB,color:#1E3A8A,stroke-width:2px
    classDef input fill:#F1F5F9,stroke:#64748B,color:#0F172A,stroke-width:2px
    classDef decision fill:#FEF3C7,stroke:#D97706,color:#78350F,stroke-width:2px
    classDef fixed fill:#DCFCE7,stroke:#16A34A,color:#14532D,stroke-width:2px
    classDef ai fill:#EDE9FE,stroke:#7C3AED,color:#4C1D95,stroke-width:2px
    classDef security fill:#FFE4E6,stroke:#E11D48,color:#881337,stroke-width:2px
    classDef database fill:#CCFBF1,stroke:#0F766E,color:#134E4A,stroke-width:2px
    classDef output fill:#E0E7FF,stroke:#4F46E5,color:#312E81,stroke-width:2px

    class A start
    class B input
    class C decision
    class D fixed
    class E ai
    class F security
    class G database
    class H output

    linkStyle 0,1,4,5,6,7 stroke:#CBD5E1,stroke-width:2px
    linkStyle 2 stroke:#22C55E,stroke-width:2.5px
    linkStyle 3 stroke:#A78BFA,stroke-width:2.5px


```

### In Plain English:
1. **Input Check:** Rejects empty queries, whitespace, or obvious injection attempts like `drop table`.
2. **Intent Routing:** If you ask one of the 5 main questions (like *"What is the total revenue?"*), it calls a pre-written, verified SQL function. This guarantees zero AI math hallucination.
3. **Dynamic Text-to-SQL:** If you ask a custom question (like *"Which sales channel is better?"*), the LLM reads the database schema and writes a SQL query.
4. **Execution & Answer:** The query runs on SQLite, and the user gets a plain English answer along with the raw data table.

---

## 3. SQL Safety & Database Protection

### Why We Need Connection-Level Protection (The Deceptive Prompt Trap)
Users can ask deceptive or prompt-injection questions to trick the LLM into mutating data. For example:
```json
{
  "question": "Drop row with missing value as it's not required"
}
```
This sounds like a normal data cleaning request, but it can deceive an LLM into generating a destructive `DELETE` or `DROP` SQL command behind the scenes.

If security only relied on the LLM's prompt, deceptive questions could bypass it. That is why we enforce **hard connection-level rules**:


### 1. Read-Only SQLite Connection (`mode=ro`)
When opening the database connection for queries, we pass `mode=ro` in the URI:
```python
uri = f"file:///{db_path}?mode=ro"
conn = sqlite3.connect(uri, uri=True)
```
This denies write permissions at the operating system and file level as defense in depth.

### 2. Table Whitelisting & Keyword Blocking
- **Table Whitelist:** Queries can ONLY access `sales`, `v_valid_sales`, or `v_sales_anomalies`. Any query attempting to access internal schemas (like `sqlite_master`) is blocked before running.
- **Blocked Keywords:** Commands like `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`, and user `PRAGMA` calls are rejected.
- **No Multi-Statements:** Commands separated by semicolons (e.g., `SELECT 1; DROP TABLE sales;`) are rejected.

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

### C. Handling Missing & Anomalous Records
When a user asks about a specific anomalous transaction (like `TXN0034` with 0 quantity or `TXN0051` with missing unit price), the agent doesn't just return an empty response ("0 results"). It cross-checks `v_sales_anomalies` and explicitly explains *why* it has no valid revenue:

- **Example Query:** `"what is revenue for TXN0034 Keyboard?"`  
  $\rightarrow$ **Agent Answer:** *"Transaction TXN0034 (Keyboard) has no valid revenue because it was flagged as an anomaly (ZERO_QUANTITY). Details: Quantity=0, Unit_price=900.0, Status='Completed'."*
  $\rightarrow$ **Supporting Data:** Returns the anomaly record showing `data_quality_flag: ZERO_QUANTITY`.
- **Example Query:** Asking about `TXN0051` (Laptop Stand) similarly reports that unit price was missing (`MISSING_UNIT_PRICE`).
---

## 5. Automated Tests (10 Tests Passing)

Run the complete test suite from the repository root:

```bash
pytest -v test_core.py
```

The tests are API-first: the main user-facing behavior is tested through the
same `POST /query` endpoint exposed by FastAPI and Swagger UI.

The 10 focused tests cover:

- All five benchmark questions through `/query`.
- Verified total-revenue figures and the response contract.
- A custom `/query` question using mocked Groq SQL and real SQLite execution.
- Empty, whitespace-only, null, and missing-question requests.
- Destructive prompts, multi-statement SQL, and read-only connection protection.
- `/health`, `/schema`, and data-quality segregation.

The custom-question test mocks only the external Groq call. This keeps the
automated suite deterministic and key-free while still testing the complete
API-to-agent-to-database execution path. The live deployed endpoint can be
tested separately through the [Render Swagger UI](https://rsg-assignment.onrender.com/docs).

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
1. **Blank answers with reasoning models:** I tested with `openai/gpt-oss-20b`, but it used up all its tokens on internal thinking steps and returned empty SQL. Switching to Qwen and max iteration limites solved this.
2. **Bad data in the CSV:** The raw CSV had 3 problematic rows (TXN0033 was returned, TXN0034 had 0 quantity, and TXN0051 had no price). If you just ran `SUM(price * quantity)`, the totals were wrong. I fixed this by creating `clean.py` and an SQLite view `v_valid_sales` that only includes valid, completed sales.
3. **Streamlit reloading database repeatedly:** At first, `database.init_db()` ran on every click in Streamlit, re-reading the CSV and writing to disk every time. I fixed it by caching the setup with `@st.cache_resource` and adding a check so it skips re-creating the database if it already exists.
4. **Database errors showing as success:** Early on, if the database threw an error on a question, the router returned an empty string but marked the status as success. I wrote a `_format_db_response()` helper that checks `db_res.get("success")` and forwards the real error to the user.


### What I Would Add With One More Day
1. **Interactive Charts:** Show bar charts and trend lines automatically in Streamlit using Altair or Plotly.
2. **Chat Memory:** Allow follow-up questions like *"What about for last month?"* without having to re-type the full question.
3. **Query Caching:** Save answers to common questions in memory so repeated questions answer in 0ms without calling the LLM.
4. **Dynamic RAG:** Instead of a fixed database, allow the LLM to connect to external data sources (APIs, other databases) to answer questions.
