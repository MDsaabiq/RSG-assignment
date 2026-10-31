"""
Database Management & Deterministic Analytics Engine for Sales BI Assistant.

Responsibilities:
1. SQLite ingestion from cleaned sales data (with views for valid and anomalous records).
2. SQL Safety & Sandbox Guards (strict read-only SELECT validation, injection prevention).
3. Deterministic query execution with structured output dictionaries.
4. Pre-built analytical tools for core business intelligence benchmarks.
"""

import os
import re
import sqlite3
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

DB_PATH = "sales.db"
CLEANED_CSV_PATH = os.path.join("data", "cleaned.csv")
RAW_CSV_PATH = os.path.join("data", "ai_bi_assistant_sales_data - GET.csv")


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Returns an SQLite read-write connection configured with Row factory (used for ingestion)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_readonly_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """
    Returns an SQLite connection in strict read-only mode at the OS/C-library level
    with PRAGMA query_only = ON as defense in depth against any mutation attempt.
    """
    abs_path = os.path.abspath(db_path)
    # SQLite URI syntax requires forward slashes on Windows
    norm_path = abs_path.replace("\\", "/")
    uri = f"file:///{norm_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON;")
    return conn


def init_db(
    csv_path: str = CLEANED_CSV_PATH,
    db_path: str = DB_PATH,
    force_reload: bool = False
) -> Dict[str, Any]:
    """
    Initializes SQLite database from cleaned CSV data.
    Creates table 'sales', view 'v_valid_sales', and view 'v_sales_anomalies'.
    """
    try:
        # If database already exists and has records, avoid re-reading CSV and re-writing table
        if os.path.exists(db_path) and not force_reload:
            try:
                with get_connection(db_path) as conn:
                    cursor = conn.cursor()
                    # Verify sales table and v_valid_sales view exist and have data
                    cursor.execute("SELECT COUNT(*) FROM sales")
                    total_count = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM v_valid_sales")
                    valid_count = cursor.fetchone()[0]
                    if total_count > 0:
                        return {
                            "success": True,
                            "db_path": db_path,
                            "total_records": total_count,
                            "valid_records": valid_count,
                            "anomaly_records": total_count - valid_count,
                            "error": None
                        }
            except Exception:
                # If table or view is missing or corrupted, fall through to re-create
                pass

        # Check if CSV exists; if not, attempt to run clean.py pipeline
        if not os.path.exists(csv_path):
            if os.path.exists(RAW_CSV_PATH):
                from clean import run_cleaning_pipeline
                run_cleaning_pipeline(input_csv=RAW_CSV_PATH, output_csv=csv_path)
            else:
                return {
                    "success": False,
                    "error": f"Neither cleaned CSV ({csv_path}) nor raw CSV ({RAW_CSV_PATH}) found.",
                    "total_records": 0
                }

        df = pd.read_csv(csv_path)

        with get_connection(db_path) as conn:
            # Load full cleaned sales table
            df.to_sql("sales", conn, if_exists="replace", index=False)

            # Create Indexes for query performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_month ON sales(order_month);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_product ON sales(Product);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_region ON sales(Region);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_valid ON sales(is_valid_sale);")

            # Create Views: v_valid_sales (filtered completed sales) & v_sales_anomalies (flagged records)
            conn.execute("DROP VIEW IF EXISTS v_valid_sales;")
            conn.execute("""
                CREATE VIEW v_valid_sales AS
                SELECT * FROM sales
                WHERE is_valid_sale = 1 AND Status = 'Completed';
            """)

            conn.execute("DROP VIEW IF EXISTS v_sales_anomalies;")
            conn.execute("""
                CREATE VIEW v_sales_anomalies AS
                SELECT * FROM sales
                WHERE is_valid_sale = 0 OR Status != 'Completed';
            """)
            conn.commit()

            cursor = conn.execute("SELECT COUNT(*) FROM sales")
            total_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM v_valid_sales")
            valid_count = cursor.fetchone()[0]

        return {
            "success": True,
            "db_path": db_path,
            "total_records": total_count,
            "valid_records": valid_count,
            "anomaly_records": total_count - valid_count,
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Database initialization failed: {str(e)}",
            "total_records": 0,
            "valid_records": 0
        }


def validate_sql(sql: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Validates that a generated SQL query is strictly read-only and safe to execute.
    Rejects empty queries, destructive statements, multiple statements, and administrative commands.
    """
    if sql is None or not str(sql).strip():
        return False, "Query is empty or null."

    cleaned_sql = sql.strip()

    # Remove SQL line comments (-- ...) and block comments (/* ... */)
    cleaned_sql = re.sub(r"--.*?\n", " ", cleaned_sql)
    cleaned_sql = re.sub(r"/\*.*?\*/", " ", cleaned_sql, flags=re.DOTALL)
    cleaned_sql = cleaned_sql.strip()

    # Prevent SQL multi-statement injection (e.g. SELECT 1; DROP TABLE ...)
    # Allow a single trailing semicolon, but no interior semicolons
    statements = [s.strip() for s in cleaned_sql.split(";") if s.strip()]
    if len(statements) > 1:
        return False, "Multi-statement execution is disallowed for security."
    elif len(statements) == 1:
        single_query = statements[0]
    else:
        return False, "No valid SQL query found."

    # Must start with SELECT or WITH (common table expressions)
    upper_query = single_query.upper()
    if not (upper_query.startswith("SELECT") or upper_query.startswith("WITH")):
        return False, "Only read-only SELECT and WITH statements are permitted."

    # Disallow destructive or schema-altering commands
    disallowed_keywords = [
        r"\bDROP\b", r"\bDELETE\b", r"\bUPDATE\b", r"\bINSERT\b",
        r"\bALTER\b", r"\bTRUNCATE\b", r"\bREPLACE\b", r"\bCREATE\b",
        r"\bEXEC\b", r"\bEXECUTE\b", r"\bPRAGMA\b", r"\bATTACH\b",
        r"\bDETACH\b", r"\bGRANT\b", r"\bREVOKE\b", r"\bVACUUM\b"
    ]
    for pattern in disallowed_keywords:
        if re.search(pattern, upper_query):
            keyword = pattern.replace(r"\b", "")
            return False, f"Prohibited SQL keyword detected: {keyword}."

    # Restrict queries strictly to expected sales tables and views
    allowed_tables = {"sales", "v_valid_sales", "v_sales_anomalies"}
    from_matches = re.findall(r"\b(?:FROM|JOIN)\s+([a-zA-Z_0-9]+)", upper_query)
    for tbl in from_matches:
        if tbl.lower() not in allowed_tables:
            return False, f"Access to table or view '{tbl}' is disallowed."

    return True, None


def execute_safe_query(
    sql: str,
    db_path: str = DB_PATH,
    max_rows: int = 200
) -> Dict[str, Any]:
    """
    Validates and executes a safe read-only SQL query against SQLite database.
    Returns structured dictionary with column headers, row data, and error status.
    Guaranteed not to raise unhandled exceptions.
    """
    # 1. SQL Safety Validation
    is_valid, validation_error = validate_sql(sql)
    if not is_valid:
        return {
            "success": False,
            "query": sql,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "error": validation_error
        }

    # Ensure DB is initialized
    if not os.path.exists(db_path):
        init_res = init_db(db_path=db_path)
        if not init_res.get("success", False):
            return {
                "success": False,
                "query": sql,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": f"Database not found and initialization failed: {init_res.get('error')}"
            }

    # Clean statement for execution
    cleaned_query = sql.strip().rstrip(";")

    try:
        with get_readonly_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(cleaned_query)

            columns = [col[0] for col in cursor.description] if cursor.description else []
            fetched_rows = cursor.fetchmany(max_rows)

            # Convert sqlite3.Row objects to standard python dictionaries
            rows = [dict(row) for row in fetched_rows]

            return {
                "success": True,
                "query": cleaned_query,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "error": None
            }
    except sqlite3.Error as e:
        return {
            "success": False,
            "query": cleaned_query,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "error": f"Database execution error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "query": cleaned_query,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "error": f"Unexpected error during query execution: {str(e)}"
        }


def get_schema_info(db_path: str = DB_PATH) -> str:
    """
    Returns structured database schema, view definitions, and field rules
    for LLM prompt context and dynamic Text-to-SQL generation.
    """
    schema_prompt = """
Database Schema (SQLite):
-------------------------
Table: sales (all raw and normalized transactions, 51 records)
View: v_valid_sales (RECOMMENDED for business analytics; filters is_valid_sale = 1 AND Status = 'Completed')
View: v_sales_anomalies (records with missing price, zero quantity, or returned status)

Columns in v_valid_sales and sales:
- Transaction_Id (TEXT): Unique transaction identifier (e.g., 'TXN0001')
- Order_date (TEXT): Original date format 'DD-MM-YYYY'
- iso_date (TEXT): Standardized date in ISO format 'YYYY-MM-DD' (Use for date range filtering)
- order_month (TEXT): Month in 'YYYY-MM' format (e.g., '2026-01', '2026-02', etc. Use for monthly aggregations)
- Product (TEXT): Product name ('Monitor', 'Desk', 'Office Chair', 'USB-C Hub', 'Wireless Mouse', 'Keyboard', 'Laptop Stand')
- Category (TEXT): Product category ('Electronics', 'Furniture', 'Accessories')
- Region (TEXT): Sales region ('North', 'South', 'East', 'West')
- Sales_channel (TEXT): Channel ('Online', 'Retail')
- Quantity (INTEGER): Cleaned units sold (> 0)
- Unit_price (REAL): Price per unit in currency
- Discount_amount (REAL): Discount given on the order
- Status (TEXT): 'Completed' or 'Returned'
- is_valid_sale (INTEGER): 1 if transaction is valid and completed; 0 if returned/anomaly
- data_quality_flag (TEXT): 'VALID' or reasons flagged (e.g. 'STATUS_RETURNED', 'ZERO_QUANTITY', 'MISSING_UNIT_PRICE')
- gross_revenue (REAL): Quantity * Unit_price
- net_revenue (REAL): gross_revenue - Discount_amount (Primary metric for business revenue)

Key Guidelines for Query Generation:
1. Always query from 'v_valid_sales' unless the user specifically asks for returned items or data quality anomalies.
2. For 'total revenue' or 'revenue', aggregate SUM(net_revenue) as total_revenue.
3. For monthly trends, GROUP BY order_month ORDER BY order_month ASC.
4. Only output safe read-only SELECT statements. Do not use UPDATE, DELETE, or DROP.
"""
    return schema_prompt.strip()


# ==============================================================================
# Deterministic Analytics Methods (Addressing Challenge Questions 1-5 Directly)
# ==============================================================================

def get_total_revenue(db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Challenge Q1: What is the total revenue?
    Calculates total gross revenue, total discounts, and total net revenue on valid completed sales.
    """
    sql = """
        SELECT 
            ROUND(SUM(gross_revenue), 2) AS total_gross_revenue,
            ROUND(SUM(Discount_amount), 2) AS total_discounts,
            ROUND(SUM(net_revenue), 2) AS total_net_revenue,
            COUNT(*) AS total_transactions
        FROM v_valid_sales;
    """
    result = execute_safe_query(sql, db_path=db_path)
    if result.get("success", False) and result.get("rows"):
        metrics = result["rows"][0]
        result["summary_text"] = (
            f"The total net revenue is ${metrics.get('total_net_revenue', 0):,.2f} "
            f"(Gross: ${metrics.get('total_gross_revenue', 0):,.2f}, "
            f"Discounts: ${metrics.get('total_discounts', 0):,.2f}) "
            f"across {metrics.get('total_transactions', 0)} completed transactions."
        )
    return result


def get_top_product(limit: int = 1, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Challenge Q2: Which product generated the highest revenue?
    Returns top-ranked product(s) by total net revenue.
    """
    sql = f"""
        SELECT 
            Product,
            Category,
            SUM(Quantity) AS total_units_sold,
            ROUND(SUM(net_revenue), 2) AS total_revenue
        FROM v_valid_sales
        GROUP BY Product, Category
        ORDER BY total_revenue DESC
        LIMIT {max(1, int(limit))};
    """
    result = execute_safe_query(sql, db_path=db_path)
    if result.get("success", False) and result.get("rows"):
        top_item = result["rows"][0]
        result["summary_text"] = (
            f"The top-performing product is '{top_item.get('Product')}' "
            f"({top_item.get('Category')}) generating ${top_item.get('total_revenue', 0):,.2f} "
            f"in net revenue ({top_item.get('total_units_sold', 0)} units sold)."
        )
    return result


def get_monthly_revenue_trend(db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Challenge Q3: What is the monthly revenue trend?
    Returns monthly aggregated net revenue, order volume, and month-over-month growth.
    """
    sql = """
        SELECT 
            order_month,
            COUNT(*) AS transaction_count,
            SUM(Quantity) AS total_units,
            ROUND(SUM(net_revenue), 2) AS monthly_revenue
        FROM v_valid_sales
        GROUP BY order_month
        ORDER BY order_month ASC;
    """
    result = execute_safe_query(sql, db_path=db_path)
    if result.get("success", False) and result.get("rows"):
        rows = result["rows"]
        # Compute month-over-month percentage change deterministically
        enhanced_rows = []
        prev_rev = None
        for r in rows:
            rev = r.get("monthly_revenue", 0.0)
            if prev_rev is not None and prev_rev > 0:
                mom_change = round(((rev - prev_rev) / prev_rev) * 100, 2)
            else:
                mom_change = 0.0
            r["mom_growth_percent"] = mom_change
            prev_rev = rev
            enhanced_rows.append(r)
        result["rows"] = enhanced_rows
        result["columns"].append("mom_growth_percent")
        result["summary_text"] = f"Monthly revenue trends calculated across {len(rows)} recorded months."
    return result


def get_top_region(limit: int = 1, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Challenge Q4: Which region generated the highest sales?
    Returns top sales region by total net revenue and sales volume.
    """
    sql = f"""
        SELECT 
            Region,
            COUNT(*) AS transaction_count,
            SUM(Quantity) AS total_units_sold,
            ROUND(SUM(net_revenue), 2) AS total_revenue
        FROM v_valid_sales
        GROUP BY Region
        ORDER BY total_revenue DESC
        LIMIT {max(1, int(limit))};
    """
    result = execute_safe_query(sql, db_path=db_path)
    if result.get("success", False) and result.get("rows"):
        top_region = result["rows"][0]
        result["summary_text"] = (
            f"The '{top_region.get('Region')}' region generated the highest sales, "
            f"producing ${top_region.get('total_revenue', 0):,.2f} in net revenue "
            f"across {top_region.get('transaction_count', 0)} orders."
        )
    return result


def compare_monthly_revenue(
    month_a: str,
    month_b: str,
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    """
    Challenge Q5: How did revenue change between two months?
    Computes absolute difference and percentage change between any two given months (e.g., '2026-01' and '2026-02').
    """
    # Sanitize month strings (expecting YYYY-MM)
    m_a = re.sub(r"[^0-9\-]", "", str(month_a).strip())
    m_b = re.sub(r"[^0-9\-]", "", str(month_b).strip())

    sql = f"""
        SELECT 
            order_month,
            ROUND(SUM(net_revenue), 2) AS total_revenue,
            COUNT(*) AS transaction_count
        FROM v_valid_sales
        WHERE order_month IN ('{m_a}', '{m_b}')
        GROUP BY order_month
        ORDER BY order_month ASC;
    """
    result = execute_safe_query(sql, db_path=db_path)
    if not result.get("success", False):
        return result

    data_map = {r.get("order_month"): r.get("total_revenue", 0.0) for r in result.get("rows", [])}
    rev_a = data_map.get(m_a, 0.0)
    rev_b = data_map.get(m_b, 0.0)

    diff = round(rev_b - rev_a, 2)
    pct_change = round((diff / rev_a * 100), 2) if rev_a > 0 else 0.0

    trend = "an increase" if diff > 0 else "a decrease" if diff < 0 else "no change"

    comparison_data = [
        {"Month": m_a, "Net Revenue": rev_a},
        {"Month": m_b, "Net Revenue": rev_b},
        {"Difference ($)": diff, "Growth (%)": pct_change}
    ]

    result["comparison"] = {
        "month_a": m_a,
        "revenue_a": rev_a,
        "month_b": m_b,
        "revenue_b": rev_b,
        "difference": diff,
        "percentage_change": pct_change,
        "trend": trend
    }
    result["rows"] = comparison_data
    result["columns"] = ["Month", "Net Revenue", "Difference ($)", "Growth (%)"]
    result["summary_text"] = (
        f"Revenue between {m_a} (${rev_a:,.2f}) and {m_b} (${rev_b:,.2f}) showed "
        f"{trend} of ${abs(diff):,.2f} ({pct_change:+,.2f}%)."
    )
    return result


def get_data_quality_audit(db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Data Management & Anomaly Audit:
    Returns breakdown of valid vs flagged records for evaluation compliance.
    """
    sql = """
        SELECT 
            data_quality_flag,
            COUNT(*) AS record_count,
            ROUND(SUM(gross_revenue), 2) AS gross_revenue_impact
        FROM sales
        GROUP BY data_quality_flag
        ORDER BY record_count DESC;
    """
    return execute_safe_query(sql, db_path=db_path)


if __name__ == "__main__":
    print("=== Initializing Database ===")
    init_res = init_db()
    print("Init Result:", init_res)

    print("\n=== Challenge Q1: Total Revenue ===")
    print(get_total_revenue().get("summary_text"))

    print("\n=== Challenge Q2: Top Product ===")
    print(get_top_product().get("summary_text"))

    print("\n=== Challenge Q3: Monthly Trend ===")
    trend = get_monthly_revenue_trend()
    for row in trend.get("rows", []):
        print(f"  {row['order_month']}: ${row['monthly_revenue']:,.2f} (MoM: {row.get('mom_growth_percent')}%)")

    print("\n=== Challenge Q4: Top Region ===")
    print(get_top_region().get("summary_text"))

    print("\n=== Challenge Q5: Month Comparison (Jan vs Feb 2026) ===")
    print(compare_monthly_revenue("2026-01", "2026-02").get("summary_text"))

    print("\n=== Safety Check: Attempting DROP TABLE ===")
    drop_test = execute_safe_query("DROP TABLE sales;")
    print("Drop Test Success:", drop_test.get("success"), "| Error:", drop_test.get("error"))
