"""
One pure function per candidate feature named in your confirmed `feature_spec.md`.

Each function:
- Is independent of any I/O (takes already-loaded DataFrames in, returns a Series/DataFrame out).
- Handles the zero-activity case explicitly per the default stated in feature_spec.md.
- Only touches the source(s) feature_spec.md names for that feature.
- Explicitly takes `as_of` as an anchor parameter (never hardcoded).
"""

from typing import Sequence
import numpy as np
import pandas as pd


def compute_days_since_last_txn(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: str | pd.Timestamp,
) -> pd.Series:
    """Feature 1: days_since_last_txn.

    - Source: transactions.db: txn_timestamp
    - Computation: (as_of - max(txn_timestamp)).days for customers with >= 1 txn up to as_of
    - Zero-activity default: 9999.0
    - Returns Series indexed by customer_id named 'days_since_last_txn'.
    """
    as_of_dt = pd.to_datetime(as_of)
    # Filter transactions strictly on or before as_of
    prior_txns = transactions[transactions["txn_timestamp"] <= as_of_dt]

    if not prior_txns.empty:
        last_txn = prior_txns.groupby("customer_id")["txn_timestamp"].max()
        days_diff = (as_of_dt - last_txn).dt.total_seconds() / 86400.0
    else:
        days_diff = pd.Series(dtype=float)

    # Reindex over all customers in `customers`
    all_cust_ids = customers["customer_id"].unique()
    res = days_diff.reindex(all_cust_ids, fill_value=9999.0)
    res.name = "days_since_last_txn"
    return res


def compute_active_months_last_12m(
    customers: pd.DataFrame,
    monthly_agg: pd.DataFrame,
    as_of: str | pd.Timestamp,
) -> pd.Series:
    """Feature 2: active_months_last_12m.

    - Source: transactions_monthly_agg.parquet: txn_month
    - Computation: Count of distinct txn_month values in the 12 complete calendar
      months prior to as_of (i.e. strictly before the start of the current month).
      Window: [as_of_month_start - 12 months, as_of_month_start).
    - Zero-activity default: 0
    - Returns Series indexed by customer_id named 'active_months_last_12m'.
    """
    as_of_dt = pd.to_datetime(as_of)
    # Current month start
    cur_month_start = pd.Timestamp(year=as_of_dt.year, month=as_of_dt.month, day=1)
    window_start = cur_month_start - pd.DateOffset(months=12)

    # Filter monthly_agg to [window_start, cur_month_start) with txn_count >= 1
    in_window = monthly_agg[
        (monthly_agg["txn_month"] >= window_start)
        & (monthly_agg["txn_month"] < cur_month_start)
        & (monthly_agg["txn_count"] >= 1)
    ]

    active_counts = in_window.groupby("customer_id")["txn_month"].nunique()

    all_cust_ids = customers["customer_id"].unique()
    res = active_counts.reindex(all_cust_ids, fill_value=0).astype(int)
    res.name = "active_months_last_12m"
    return res


def compute_spend_trajectory(
    customers: pd.DataFrame,
    monthly_agg: pd.DataFrame,
    as_of: str | pd.Timestamp,
    recent_window_months: int = 3,
) -> pd.Series:
    """Feature 3: spend_trajectory (versioned).

    - Source: transactions_monthly_agg.parquet: total_amount
    - Parameter: recent_window_months (v1=3, v2=6, v3=2). Baseline window has same length.
    - Computation:
        recent_window: [cur_month_start - recent_window_months, cur_month_start)
        baseline_window: [cur_month_start - 2 * recent_window_months, cur_month_start - recent_window_months)
        Mean monthly spend = sum(total_amount in window) / recent_window_months.
        Ratio = recent_mean / baseline_mean.
        If baseline_mean == 0:
            if recent_mean == 0 -> 1.0 (no change)
            if recent_mean > 0 -> 1.0 (or capped trajectory; 1.0 default for zero-baseline)
    - Zero-activity default: 1.0 (no change)
    - Returns Series indexed by customer_id named 'spend_trajectory'.
    """
    as_of_dt = pd.to_datetime(as_of)
    cur_month_start = pd.Timestamp(year=as_of_dt.year, month=as_of_dt.month, day=1)
    recent_start = cur_month_start - pd.DateOffset(months=recent_window_months)
    baseline_start = recent_start - pd.DateOffset(months=recent_window_months)

    # Recent window
    recent_df = monthly_agg[
        (monthly_agg["txn_month"] >= recent_start)
        & (monthly_agg["txn_month"] < cur_month_start)
    ]
    recent_spend = recent_df.groupby("customer_id")["total_amount"].sum()

    # Baseline window
    baseline_df = monthly_agg[
        (monthly_agg["txn_month"] >= baseline_start)
        & (monthly_agg["txn_month"] < recent_start)
    ]
    baseline_spend = baseline_df.groupby("customer_id")["total_amount"].sum()

    all_cust_ids = customers["customer_id"].unique()
    r_sum = recent_spend.reindex(all_cust_ids, fill_value=0.0)
    b_sum = baseline_spend.reindex(all_cust_ids, fill_value=0.0)

    # Calculate means
    r_mean = r_sum / float(recent_window_months)
    b_mean = b_sum / float(recent_window_months)

    # Compute ratio
    ratio = np.where(
        b_mean > 0,
        r_mean / b_mean,
        1.0,  # zero baseline or zero activity default is 1.0 (neutral trajectory)
    )

    res = pd.Series(ratio, index=all_cust_ids, name="spend_trajectory", dtype=float)
    return res


def compute_return_rate(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: str | pd.Timestamp,
    window_days: int = 180,
) -> pd.Series:
    """Feature 4: return_rate (rolling windowed).

    - Source: transactions.db: is_returned
    - Computation: SUM(is_returned) / COUNT(*) in (as_of - window_days, as_of].
    - Zero-activity default: 0.0
    - Returns Series indexed by customer_id named 'return_rate'.
    """
    as_of_dt = pd.to_datetime(as_of)
    window_start = as_of_dt - pd.Timedelta(days=window_days)

    in_window = transactions[
        (transactions["txn_timestamp"] > window_start)
        & (transactions["txn_timestamp"] <= as_of_dt)
    ]

    if not in_window.empty:
        ret_sum = in_window.groupby("customer_id")["is_returned"].sum()
        total_cnt = in_window.groupby("customer_id")["is_returned"].count()
        rate = ret_sum / total_cnt
    else:
        rate = pd.Series(dtype=float)

    all_cust_ids = customers["customer_id"].unique()
    res = rate.reindex(all_cust_ids, fill_value=0.0).fillna(0.0)
    res.name = "return_rate"
    return res


def compute_txn_count_last_nd(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: str | pd.Timestamp,
    window_days: int = 90,
) -> pd.Series:
    """Feature 5: txn_count_last_Nd (versioned).

    - Source: transactions.db: txn_timestamp
    - Parameter: window_days (v1=180, v2=90)
    - Computation: count of txn_timestamp in (as_of - window_days, as_of].
    - Zero-activity default: 0
    - Returns Series indexed by customer_id named 'txn_count_last_Nd'.
    """
    as_of_dt = pd.to_datetime(as_of)
    window_start = as_of_dt - pd.Timedelta(days=window_days)

    in_window = transactions[
        (transactions["txn_timestamp"] > window_start)
        & (transactions["txn_timestamp"] <= as_of_dt)
    ]

    counts = in_window.groupby("customer_id")["txn_timestamp"].count()

    all_cust_ids = customers["customer_id"].unique()
    res = counts.reindex(all_cust_ids, fill_value=0).astype(int)
    res.name = "txn_count_last_Nd"
    return res


def compute_tenure_days(
    customers: pd.DataFrame,
    as_of: str | pd.Timestamp,
) -> pd.Series:
    """Feature 6: tenure_days.

    - Source: customers.csv: signup_date
    - Computation: max(0.0, (as_of - signup_date).days)
    - Zero-activity default: N/A (all customers have signup_date)
    - Returns Series indexed by customer_id named 'tenure_days'.
    """
    as_of_dt = pd.to_datetime(as_of)
    signup = pd.to_datetime(customers.set_index("customer_id")["signup_date"])
    tenure = (as_of_dt - signup).dt.total_seconds() / 86400.0
    # Guard against future signups relative to historical as_of dates (e.g. training window anchor)
    tenure = tenure.clip(lower=0.0)

    res = tenure.astype(float)
    res.name = "tenure_days"
    return res
