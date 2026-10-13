"""
The ONE shared feature-build entry point. Both `scripts/build_training_features.py`
(training path: a historical as-of date, batch of many customers) and
`scripts/score_customer.py` (scoring path: single customer_id, same as-of date) must call
this same function — that is the entire train/score parity guarantee for this pipeline.

There must be exactly one code path here. If you find yourself writing separate logic for
"training mode" vs. "scoring mode" beyond which rows they select at the end, that is a
parity bug — go back and unify it rather than special-casing either path.
"""

from typing import Any
import pandas as pd

from features import ingest, transforms


DEFAULT_SOURCE_PATHS = {
    "customers": "data/customers.csv",
    "transactions": "data/transactions.db",
    "monthly_agg": "data/transactions_monthly_agg.parquet",
}


def build_features(
    as_of: str,
    source_paths: dict[str, str] | None = None,
    customer_ids: list[int] | None = None,
    parameters: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Build the full feature set as of `as_of` for either the whole customer base
    (training path, `customer_ids=None`) or a specific subset (scoring path, one or more
    `customer_ids`).

    - Defaults `source_paths` to the standard data/ locations.
    - Loads all three sources via features/ingest.py — no direct file I/O here.
    - Runs all pure feature transforms from features/transforms.py identically.
    - Combines features into a single DataFrame.
    - Filters to `customer_ids` if provided; otherwise uses the full customer base.
      This filtering is the ONLY difference allowed between training and scoring call sites.
    - Returns a DataFrame with one row per customer_id, plus `customer_id` and `as_of_date`.
    """
    paths = dict(DEFAULT_SOURCE_PATHS)
    if source_paths:
        paths.update(source_paths)

    # 1. Pure ingestion
    customers_df = ingest.load_customers(paths["customers"])
    transactions_df = ingest.load_transactions(paths["transactions"])
    monthly_agg_df = ingest.load_monthly_agg(paths["monthly_agg"])

    # Extract transform parameters with defaults matching latest feature_spec.md
    params = parameters or {}
    window_days_nd = params.get("txn_count_last_Nd__window_days", 90)
    recent_window_months_traj = params.get("spend_trajectory__recent_window_months", 6)
    return_window_days = params.get("return_rate__window_days", 180)

    # 2. Pure transforms run identically on the entire population
    f_recency = transforms.compute_days_since_last_txn(customers_df, transactions_df, as_of)
    f_active_months = transforms.compute_active_months_last_12m(customers_df, monthly_agg_df, as_of)
    f_traj = transforms.compute_spend_trajectory(
        customers_df, monthly_agg_df, as_of, recent_window_months=recent_window_months_traj
    )
    f_return_rate = transforms.compute_return_rate(
        customers_df, transactions_df, as_of, window_days=return_window_days
    )
    f_txn_count = transforms.compute_txn_count_last_nd(
        customers_df, transactions_df, as_of, window_days=window_days_nd
    )
    f_tenure = transforms.compute_tenure_days(customers_df, as_of)

    # 3. Assemble full feature DataFrame
    features_df = pd.DataFrame(
        {
            "customer_id": customers_df["customer_id"].values,
            "days_since_last_txn": f_recency.values,
            "active_months_last_12m": f_active_months.values,
            "spend_trajectory": f_traj.values,
            "return_rate": f_return_rate.values,
            "txn_count_last_Nd": f_txn_count.values,
            "tenure_days": f_tenure.values,
            "as_of_date": as_of,
        }
    )

    # 4. Filter by customer_ids if specified (sole difference between training and scoring)
    if customer_ids is not None:
        missing_ids = set(customer_ids) - set(features_df["customer_id"])
        if missing_ids:
            raise ValueError(f"Requested customer_id(s) not found in customer base: {sorted(missing_ids)}")
        features_df = features_df[features_df["customer_id"].isin(customer_ids)].reset_index(drop=True)

    return features_df
