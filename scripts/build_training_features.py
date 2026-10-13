#!/usr/bin/env python3
"""
Builds features for the full training population as of a given date, writes a versioned
parquet feature snapshot, and registers every candidate feature into the feature store.
"""

import argparse
from pathlib import Path
import sys

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd

from features.build import build_features
from features.schema import FEATURE_SCHEMA
from features.quality_checks import run_all_checks
from features import ingest, transforms
from feature_store import store


def register_all_candidate_features(
    as_of: str,
    db_path: str = store.REGISTRY_DB,
    values_dir: str = store.VALUES_DIR,
) -> None:
    """Build and register every candidate feature per feature_spec.md.
    For the two designated versioned features:
    - txn_count_last_Nd: register v1 (window_days=180) then v2 (window_days=90)
    - spend_trajectory: register v1 (months=3) then v2 (months=6) then v3 (months=2)
    For all other features: register their base version.
    """
    customers = ingest.load_customers()
    transactions = ingest.load_transactions()
    monthly_agg = ingest.load_monthly_agg()

    # 1. Feature: days_since_last_txn
    print("Building & registering days_since_last_txn...")
    f_rec = transforms.compute_days_since_last_txn(customers, transactions, as_of)
    df_rec = pd.DataFrame(
        {"customer_id": customers["customer_id"].values, "days_since_last_txn": f_rec.values, "as_of_date": as_of}
    )
    store.register_version(
        feature_name="days_since_last_txn",
        values_df=df_rec,
        description="Days between as_of and most recent transaction.",
        source_columns="data/transactions.db:transactions.txn_timestamp",
        transform_summary="(as_of - max(txn_timestamp)).days for transactions <= as_of. Missing defaulted to 9999.0.",
        business_rationale="Longer time since last activity is a direct churn signal.",
        parameters={},
        db_path=db_path,
        values_dir=values_dir,
    )

    # 2. Feature: active_months_last_12m
    print("Building & registering active_months_last_12m...")
    f_act = transforms.compute_active_months_last_12m(customers, monthly_agg, as_of)
    df_act = pd.DataFrame(
        {"customer_id": customers["customer_id"].values, "active_months_last_12m": f_act.values, "as_of_date": as_of}
    )
    store.register_version(
        feature_name="active_months_last_12m",
        values_df=df_act,
        description="Distinct active calendar months in 12 complete months prior to as_of.",
        source_columns="data/transactions_monthly_agg.parquet:transactions_monthly_agg.txn_month,txn_count",
        transform_summary="Count of distinct txn_month where txn_count >= 1 in [as_of_month_start - 12m, as_of_month_start). Missing defaulted to 0.",
        business_rationale="Breadth of activity over a longer window captures habit and engagement consistency.",
        parameters={"window_months": 12},
        db_path=db_path,
        values_dir=values_dir,
    )

    # 3. Feature: return_rate
    print("Building & registering return_rate...")
    f_ret = transforms.compute_return_rate(customers, transactions, as_of, window_days=180)
    df_ret = pd.DataFrame(
        {"customer_id": customers["customer_id"].values, "return_rate": f_ret.values, "as_of_date": as_of}
    )
    store.register_version(
        feature_name="return_rate",
        values_df=df_ret,
        description="Share of returned transactions in rolling 180-day window ending at as_of.",
        source_columns="data/transactions.db:transactions.is_returned,txn_timestamp",
        transform_summary="SUM(is_returned) / COUNT(*) in (as_of - 180d, as_of]. Missing defaulted to 0.0.",
        business_rationale="Rising return rates reflect dissatisfaction preceding churn.",
        parameters={"window_days": 180},
        db_path=db_path,
        values_dir=values_dir,
    )

    # 4. Feature: tenure_days
    print("Building & registering tenure_days...")
    f_ten = transforms.compute_tenure_days(customers, as_of)
    df_ten = pd.DataFrame(
        {"customer_id": customers["customer_id"].values, "tenure_days": f_ten.values, "as_of_date": as_of}
    )
    store.register_version(
        feature_name="tenure_days",
        values_df=df_ten,
        description="Customer account age in days as of the as-of date.",
        source_columns="data/customers.csv:customers.signup_date",
        transform_summary="(as_of - signup_date).days computed from customers profile.",
        business_rationale="Newer customers have unproven habits and higher structural churn risk.",
        parameters={},
        db_path=db_path,
        values_dir=values_dir,
    )

    # 5. Versioned Feature: txn_count_last_Nd (v1 = 180, v2 = 90)
    print("Building & registering txn_count_last_Nd v1 (window_days=180)...")
    f_txn_v1 = transforms.compute_txn_count_last_nd(customers, transactions, as_of, window_days=180)
    df_txn_v1 = pd.DataFrame(
        {"customer_id": customers["customer_id"].values, "txn_count_last_Nd": f_txn_v1.values, "as_of_date": as_of}
    )
    store.register_version(
        feature_name="txn_count_last_Nd",
        values_df=df_txn_v1,
        description="Transaction count in trailing 180 days.",
        source_columns="data/transactions.db:transactions.txn_timestamp",
        transform_summary="COUNT(txn_timestamp) in (as_of - 180d, as_of]. Missing defaulted to 0.",
        business_rationale="Initial baseline frequency over 180-day window.",
        parameters={"window_days": 180},
        db_path=db_path,
        values_dir=values_dir,
    )

    print("Building & registering txn_count_last_Nd v2 (window_days=90)...")
    f_txn_v2 = transforms.compute_txn_count_last_nd(customers, transactions, as_of, window_days=90)
    df_txn_v2 = pd.DataFrame(
        {"customer_id": customers["customer_id"].values, "txn_count_last_Nd": f_txn_v2.values, "as_of_date": as_of}
    )
    store.register_version(
        feature_name="txn_count_last_Nd",
        values_df=df_txn_v2,
        description="Transaction count in trailing 90 days.",
        source_columns="data/transactions.db:transactions.txn_timestamp",
        transform_summary="COUNT(txn_timestamp) in (as_of - 90d, as_of]. Missing defaulted to 0.",
        business_rationale="Shortened from 180d to 90d because trailing <=90d behavior carries current purchase intent without dilution.",
        parameters={"window_days": 90},
        db_path=db_path,
        values_dir=values_dir,
    )

    # 6. Versioned Feature: spend_trajectory (v1 = 3, v2 = 6, v3 = 2)
    print("Building & registering spend_trajectory v1 (recent_window_months=3)...")
    f_tr_v1 = transforms.compute_spend_trajectory(customers, monthly_agg, as_of, recent_window_months=3)
    df_tr_v1 = pd.DataFrame(
        {"customer_id": customers["customer_id"].values, "spend_trajectory": f_tr_v1.values, "as_of_date": as_of}
    )
    store.register_version(
        feature_name="spend_trajectory",
        values_df=df_tr_v1,
        description="Spend trajectory comparing 3-month recent mean to 3-month prior baseline.",
        source_columns="data/transactions_monthly_agg.parquet:transactions_monthly_agg.total_amount,txn_month",
        transform_summary="3m recent mean / 3m baseline mean. Zero baseline or activity defaulted to 1.0.",
        business_rationale="Initial trajectory model comparing 3 recent complete months to previous 3 months.",
        parameters={"recent_window_months": 3},
        db_path=db_path,
        values_dir=values_dir,
    )

    print("Building & registering spend_trajectory v2 (recent_window_months=6)...")
    f_tr_v2 = transforms.compute_spend_trajectory(customers, monthly_agg, as_of, recent_window_months=6)
    df_tr_v2 = pd.DataFrame(
        {"customer_id": customers["customer_id"].values, "spend_trajectory": f_tr_v2.values, "as_of_date": as_of}
    )
    store.register_version(
        feature_name="spend_trajectory",
        values_df=df_tr_v2,
        description="Spend trajectory comparing 6-month recent mean to 6-month prior baseline.",
        source_columns="data/transactions_monthly_agg.parquet:transactions_monthly_agg.total_amount,txn_month",
        transform_summary="6m recent mean / 6m baseline mean. Zero baseline or activity defaulted to 1.0.",
        business_rationale="Widened from 3 to 6 months to stabilize against sparse buying frequency (~7 txns/yr).",
        parameters={"recent_window_months": 6},
        db_path=db_path,
        values_dir=values_dir,
    )

    print("Building & registering spend_trajectory v3 (recent_window_months=2)...")
    f_tr_v3 = transforms.compute_spend_trajectory(customers, monthly_agg, as_of, recent_window_months=2)
    df_tr_v3 = pd.DataFrame(
        {"customer_id": customers["customer_id"].values, "spend_trajectory": f_tr_v3.values, "as_of_date": as_of}
    )
    store.register_version(
        feature_name="spend_trajectory",
        values_df=df_tr_v3,
        description="Spend trajectory comparing 2-month recent mean to 2-month prior baseline.",
        source_columns="data/transactions_monthly_agg.parquet:transactions_monthly_agg.total_amount,txn_month",
        transform_summary="2m recent mean / 2m baseline mean. Zero baseline or activity defaulted to 1.0.",
        business_rationale="Narrowed to 2 months to isolate acute recent drops smoothed out by longer averages.",
        parameters={"recent_window_months": 2},
        db_path=db_path,
        values_dir=values_dir,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of",
        default="2026-05-03",
        help="As-of date for training feature computation (default: 2026-05-03 to prevent churn-window label leakage).",
    )
    args = parser.parse_args()

    print(f"Building training features as of {args.as_of} via features/build.py...")
    features_df = build_features(as_of=args.as_of)

    # Identify zero-activity customer IDs for validation
    cust_df = ingest.load_customers()
    txns_df = ingest.load_transactions()
    active_ids = set(txns_df[txns_df["txn_timestamp"] <= pd.to_datetime(args.as_of)]["customer_id"])
    zero_ids = list(set(cust_df["customer_id"]) - active_ids)

    print("Running quality checks...")
    results = run_all_checks(features_df, expected_row_count=1500, zero_customer_ids=zero_ids)
    print("Quality checks passed successfully!")

    print("Registering features into feature store...")
    register_all_candidate_features(as_of=args.as_of)
    print("All features and versioned snapshots successfully registered in feature store.")


if __name__ == "__main__":
    main()
