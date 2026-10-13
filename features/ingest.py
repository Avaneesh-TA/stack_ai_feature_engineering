"""
Pure I/O loaders for the three heterogeneous raw sources described in
`data_dictionary.md`. No feature logic belongs here — only loading and basic
type coercion, so ingestion can be unit-tested and swapped independently of
`transforms.py`.
"""

from pathlib import Path
import sqlite3
import pandas as pd


def load_customers(path: str = "data/customers.csv") -> pd.DataFrame:
    """Load customers.csv.

    - Reads CSV with pandas.
    - Parses `signup_date` as datetime64[ns].
    - Returns one row per customer_id (1500 rows).
    """
    df = pd.read_csv(path)
    df["signup_date"] = pd.to_datetime(df["signup_date"])
    return df


def load_transactions(path: str = "data/transactions.db") -> pd.DataFrame:
    """Load the row-level `transactions` table from the SQLite database.

    - Connects via sqlite3.
    - Casts `txn_timestamp` to datetime64[ns] (SQLite stores ISO-8601 text).
    - Casts `is_returned` to int64.
    - Returns the full row-level frame without aggregation.
    """
    conn = sqlite3.connect(path)
    try:
        df = pd.read_sql("SELECT * FROM transactions", conn)
    finally:
        conn.close()

    df["txn_timestamp"] = pd.to_datetime(df["txn_timestamp"])
    df["is_returned"] = df["is_returned"].astype(int)
    return df


def load_monthly_agg(path: str = "data/transactions_monthly_agg.parquet") -> pd.DataFrame:
    """Load the pre-aggregated customer x month parquet extract.

    - Reads parquet file with pandas / pyarrow.
    - Parses `txn_month` as datetime64[ns] (first-of-month).
    - Returns as-is (customers/months with zero activity have no row).
    """
    df = pd.read_parquet(path)
    df["txn_month"] = pd.to_datetime(df["txn_month"])
    return df
