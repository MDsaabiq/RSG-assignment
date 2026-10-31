# clean.py
import pandas as pd
import os

def run_cleaning_pipeline(input_csv: str = "./data/ai_bi_assistant_sales_data - GET.csv", output_csv: str = "./data/cleaned.csv") -> dict:
    """
    Reads raw sales transactions, normalizes fields, flags data quality anomalies,
    standardizes dates, computes revenues, and saves to cleaned.csv.
    """
    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"Input file {input_csv} not found.")

    df = pd.read_csv(input_csv)
    df.columns = [c.strip() for c in df.columns]

    # 1. Strip whitespace on string columns
    string_cols = ["Transaction_Id", "Order_date", "Product", "Category", "Region", "Sales_channel", "Status"]
    for col in string_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # 2. Coerce numeric types
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce")
    df["Unit_price"] = pd.to_numeric(df["Unit_price"], errors="coerce")
    df["Discount_amount"] = pd.to_numeric(df["Discount_amount"], errors="coerce").fillna(0.0)

    processed_rows = []
    anomaly_count = 0

    for _, row in df.iterrows():
        flags = []
        is_missing_price = int(pd.isna(row["Unit_price"]) or row["Unit_price"] <= 0)
        is_zero_qty = int(pd.isna(row["Quantity"]) or row["Quantity"] <= 0)
        is_returned = int(row["Status"] != "Completed")

        if is_missing_price:
            flags.append("MISSING_UNIT_PRICE")
        if is_zero_qty:
            flags.append("ZERO_QUANTITY")
        if is_returned:
            flags.append(f"STATUS_{row['Status'].upper()}")

        # 3. Standardize date format (DD-MM-YYYY -> YYYY-MM-DD and YYYY-MM)
        try:
            dt = pd.to_datetime(row["Order_date"], format="%d-%m-%Y")
            iso_date = dt.strftime("%Y-%m-%d")
            order_month = dt.strftime("%Y-%m")
        except Exception:
            flags.append("INVALID_DATE_FORMAT")
            iso_date = str(row["Order_date"])
            order_month = "Unknown"

        clean_qty = 0 if is_zero_qty else int(row["Quantity"])
        clean_price = 0.0 if is_missing_price else float(row["Unit_price"])
        discount = float(row["Discount_amount"])

        is_valid_sale = 1 if len(flags) == 0 else 0
        quality_flag = "VALID" if is_valid_sale else "; ".join(flags)

        if not is_valid_sale:
            anomaly_count += 1

        # 4. Compute gross and net revenue (0.0 for invalid/returned orders to preserve SUM accuracy)
        gross_rev = float(clean_qty * clean_price) if is_valid_sale else 0.0
        net_rev = float(gross_rev - discount) if is_valid_sale else 0.0

        record = {
            "Transaction_Id": row["Transaction_Id"],
            "Order_date": row["Order_date"],
            "iso_date": iso_date,
            "order_month": order_month,
            "Product": row["Product"],
            "Category": row["Category"],
            "Region": row["Region"],
            "Sales_channel": row["Sales_channel"],
            "Quantity": clean_qty,
            "Unit_price": clean_price,
            "Discount_amount": discount,
            "Status": row["Status"],
            "is_missing_price": is_missing_price,
            "is_zero_quantity": is_zero_qty,
            "is_valid_sale": is_valid_sale,
            "data_quality_flag": quality_flag,
            "gross_revenue": gross_rev,
            "net_revenue": net_rev
        }
        processed_rows.append(record)

    cleaned_df = pd.DataFrame(processed_rows)
    cleaned_df.to_csv(output_csv, index=False)

    summary = {
        "total_rows_processed": len(cleaned_df),
        "valid_sales_rows": int(cleaned_df["is_valid_sale"].sum()),
        "flagged_anomaly_rows": anomaly_count,
        "output_file": output_csv
    }
    return summary

if __name__ == "__main__":
    res = run_cleaning_pipeline()
    print("=== Cleaning Pipeline Executed Successfully ===")
    for k, v in res.items():
        print(f"{k}: {v}")