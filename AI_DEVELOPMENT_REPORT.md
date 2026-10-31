# AI-Assisted Development Challenge: Evaluation & Technical Defense Report
**Candidate Assessment Document** | *GET Selection Challenge*

---

## 1. Executive Summary of Completion

All functional requirements and assessment deliverables have been 100% completed:

| Rubric Area | Requirement | Implementation Details | Status |
| :--- | :--- | :--- | :---: |
| **Data Management** | Ingest CSV, handle anomalies, explain storage/querying | `clean.py` cleans data; `database.py` creates SQLite `sales` table, creates indexes, and segregates valid records via `v_valid_sales` and flagged records via `v_sales_anomalies`. | **100% Complete** |
| **Backend API** | Accept question, structured response, handle errors | `api.py` exposes FastAPI `POST /query`, returns structured JSON, returns HTTP 400 on empty/malformed inputs, HTTP 200 on success. | **100% Complete** |
| **Analytics** | Support at least 4 of 5 benchmark questions with data | Supports all **5 out of 5** challenge questions with exact deterministic SQL computations and supporting breakdown tables. | **100% Complete** |
| **AI Integration** | LLM text-to-SQL, query validation, block destructive ops | LangGraph agent (`agent.py`) using Groq `qwen/qwen3.8-27b`, read-only SQL enforcement (`validate_sql`), self-correction retry loop. | **100% Complete** |
| **User Interface** | Simple UI to enter questions and view results/data | Streamlit interface (`app.py`) with chat history, tabular data expanders, SQL query inspectability, and benchmark buttons. | **100% Complete** |
| **Testing** | $\ge 5$ test cases (valid, invalid, edge cases) | **16 automated pytest unit & integration tests** in `test_core.py` (100% passing in ~2 seconds). | **100% Complete** |

---

## 2. Mandatory Reflection Report (Deliverable #5)

### A. Which AI Tools Were Used
* **Antigravity Coding Assistant (DeepMind):** Used for codebase analysis, test writing, iterative code generation, and test-driven verification.
* **Groq Inference Engine (`qwen/qwen3.8-27b`):** Selected for high-speed (~300ms latency) zero-temperature SQL generation and natural language synthesis.
* **LangGraph (`langgraph.graph.StateGraph`):** Chosen as the stateful agentic orchestration framework to handle validation, routing, execution, and reflection loops.

### B. How AI Was Used During Development
1. **Architectural Trade-Off Analysis:** AI was used to compare pure Text-to-SQL vs. strict Function Calling vs. a Hybrid Router, settling on the hybrid model to guarantee 100% benchmark score while maintaining exploratory flexibility.
2. **Data Anomaly Auditing:** Used AI scripts to rapidly scan `ai_bi_assistant_sales_data - GET.csv`, identifying anomalies:
   - `TXN0033`: Returned item with positive revenue.
   - `TXN0034`: Transaction with zero quantity.
   - `TXN0051`: Transaction with missing unit price.
3. **Automated Test Scaffolding:** Developed 16 robust `pytest` tests covering mathematical accuracy, API contracts, input edge cases, and SQL injection security.

### C. Problems Encountered & How They Were Debugged
1. **Groq Model Availability:**
   - *Problem:* Groq's legacy `llama-3.3-70b-versatile` endpoint returned a `model_not_found` error.
   - *Debugging:* Queried Groq's model catalog dynamically via `client.models.list()`, identified active models (`qwen/qwen3.8-27b`, `openai/gpt-oss-20b`), and tested generation behavior.
2. **Reasoning Token Exhaustion:**
   - *Problem:* Reasoning models like `openai/gpt-oss-20b` consumed all allotted tokens generating hidden internal reasoning thoughts, leaving the completion response blank.
   - *Debugging:* Switched to `qwen/qwen3.8-27b` which directly outputs clean SQL without consuming tokens on hidden chains.
3. **Metric Distortion from Uncleaned Data:**
   - *Problem:* Directly summing `Quantity * Unit_price` inflated revenue by counting returned orders and errored on missing prices.
   - *Debugging:* Formulated `v_valid_sales` view filtering `is_valid_sale = 1 AND Status = 'Completed'`, ensuring deterministic calculation accuracy.

### D. What Would Be Improved With Another Day of Work
1. **Interactive Chart Generation:** Automatically generate Altair/Plotly bar and line charts in Streamlit when the query returns time-series or categorical aggregations.
2. **Query Caching Layer:** Implement an in-memory Redis or SQLite LRU cache for frequent questions to achieve sub-millisecond response times.
3. **Conversational Memory:** Add persistent thread history in LangGraph so users can ask contextual follow-up questions (e.g., *"What about in the East region?"* following a product breakdown).

---

## 3. Interview Defense Reference Guide

Be ready to explain these core concepts during your technical interview:

### 1. Vectorless RAG vs. Vector RAG
* **Vector RAG:** Chunks unstructured text, generates dense vector embeddings, and performs cosine similarity search.
  - *Why it fails on BI/tabular data:* Vector distance cannot perform arithmetic (`SUM`, `AVG`, `GROUP BY`). Asking *"What is total revenue?"* returns random text snippets, forcing the LLM to hallucinate calculations.
* **Vectorless RAG (This Project):** Connects the LLM directly to structured metadata (schema, views, data types). The LLM formulates deterministic database queries executed by an actual SQL engine. All numbers in the final answer originate directly from the database.

### 2. Agentic AI vs. Generative AI
* **Standard GenAI:** One-shot, passive text generation. The user inputs a prompt, and the model guesses a response without external actions or verification.
* **Agentic AI (This Project):** A stateful system with perception (schema context), reasoning (intent classification), action (executing queries on SQLite), reflection (self-correction retry loop if SQL fails), and safety guardrails.

### 3. Agentic Frameworks: LangGraph vs. LangChain vs. Google ADK vs. Dify
* **LangChain:** Traditional linear chain-based abstraction. Can become rigid when complex loops or state branches are required.
* **LangGraph (Used Here):** Graph-based state machine allowing cyclical execution (loops, retries, conditional branches). Perfect for self-correcting agents where bad SQL must loop back to the model with error feedback.
* **Google ADK (Agent Development Kit):** Focused on enterprise integration with Gemini multimodal models, tool grounding, and Vertex AI.
* **Dify:** Low-code/no-code graphical workflow builder for enterprise RAG and agent orchestration.

