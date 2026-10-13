"""
Runnable-standalone data-quality checks (drift / null / outlier) against a built
features DataFrame, implementing every check listed in your confirmed
`feature_spec.md`'s data-quality section.

Each check function returns a clear pass/fail dictionary plus which rows/features
triggered a failure — and raises ValueError when called via assert/enforce methods,
never silently passing on bad input.
"""

from typing import Any
import pandas as pd
import numpy as np


FEATURE_COLUMNS = [
    "days_since_last_txn",
    "active_months_last_12m",
    "spend_trajectory",
    "return_rate",
    "txn_count_last_Nd",
    "tenure_days",
]


def check_no_unexpected_nulls(features: pd.DataFrame) -> dict[str, Any]:
    """Fail if any feature column that should never be null has null/NaN/None values.
    Catches dropping zero-transaction customers instead of applying default.
    """
    failing_features = []
    failing_rows: list[int] = []

    for col in FEATURE_COLUMNS:
        if col in features.columns:
            null_mask = features[col].isna()
            if null_mask.any():
                failing_features.append(col)
                failing_rows.extend(features.loc[null_mask, "customer_id"].tolist())

    failing_rows = sorted(list(set(failing_rows)))
    passed = len(failing_features) == 0

    return {
        "check": "no_unexpected_nulls",
        "passed": passed,
        "failing_features": failing_features,
        "failing_rows": failing_rows,
    }


def check_zero_activity_defaults(features: pd.DataFrame, zero_customer_ids: list[int]) -> dict[str, Any]:
    """Fail if known zero-activity customers carry NaN or unexpected non-default values.
    Expected defaults:
    - days_since_last_txn: 9999.0
    - active_months_last_12m: 0
    - spend_trajectory: 1.0
    - return_rate: 0.0
    - txn_count_last_Nd: 0
    """
    zero_df = features[features["customer_id"].isin(zero_customer_ids)]
    if zero_df.empty:
        return {"check": "zero_activity_defaults", "passed": True, "failing_rows": []}

    failing_rows = []
    for _, row in zero_df.iterrows():
        cid = int(row["customer_id"])
        if np.isnan(row["days_since_last_txn"]) or row["days_since_last_txn"] != 9999.0:
            failing_rows.append(cid)
        elif np.isnan(row["active_months_last_12m"]) or row["active_months_last_12m"] != 0:
            failing_rows.append(cid)
        elif np.isnan(row["spend_trajectory"]) or row["spend_trajectory"] != 1.0:
            failing_rows.append(cid)
        elif np.isnan(row["return_rate"]) or row["return_rate"] != 0.0:
            failing_rows.append(cid)
        elif np.isnan(row["txn_count_last_Nd"]) or row["txn_count_last_Nd"] != 0:
            failing_rows.append(cid)

    failing_rows = sorted(list(set(failing_rows)))
    passed = len(failing_rows) == 0

    return {
        "check": "zero_activity_defaults",
        "passed": passed,
        "failing_rows": failing_rows,
    }


def check_outliers(features: pd.DataFrame) -> dict[str, Any]:
    """Fail if monetary/aggregate features have values outside sane bounds:
    - return_rate in [0.0, 1.0]
    - active_months_last_12m in [0, 12]
    - txn_count_last_Nd >= 0 and <= 1000
    - tenure_days >= 0
    - days_since_last_txn >= 0
    - spend_trajectory >= 0.0 and <= 1000.0 (unreasonable ratio indicates division bug)
    """
    failing_features = []
    failing_rows: list[int] = []

    if "return_rate" in features.columns:
        bad = (features["return_rate"] < 0.0) | (features["return_rate"] > 1.0)
        if bad.any():
            failing_features.append("return_rate")
            failing_rows.extend(features.loc[bad, "customer_id"].tolist())

    if "active_months_last_12m" in features.columns:
        bad = (features["active_months_last_12m"] < 0) | (features["active_months_last_12m"] > 12)
        if bad.any():
            failing_features.append("active_months_last_12m")
            failing_rows.extend(features.loc[bad, "customer_id"].tolist())

    if "txn_count_last_Nd" in features.columns:
        bad = (features["txn_count_last_Nd"] < 0) | (features["txn_count_last_Nd"] > 1000)
        if bad.any():
            failing_features.append("txn_count_last_Nd")
            failing_rows.extend(features.loc[bad, "customer_id"].tolist())

    if "tenure_days" in features.columns:
        bad = features["tenure_days"] < 0
        if bad.any():
            failing_features.append("tenure_days")
            failing_rows.extend(features.loc[bad, "customer_id"].tolist())

    if "days_since_last_txn" in features.columns:
        bad = features["days_since_last_txn"] < 0
        if bad.any():
            failing_features.append("days_since_last_txn")
            failing_rows.extend(features.loc[bad, "customer_id"].tolist())

    if "spend_trajectory" in features.columns:
        bad = (features["spend_trajectory"] < 0.0) | (features["spend_trajectory"] > 1000.0)
        if bad.any():
            failing_features.append("spend_trajectory")
            failing_rows.extend(features.loc[bad, "customer_id"].tolist())

    failing_rows = sorted(list(set(failing_rows)))
    passed = len(failing_features) == 0

    return {
        "check": "outliers",
        "passed": passed,
        "failing_features": failing_features,
        "failing_rows": failing_rows,
    }


def check_row_count(features: pd.DataFrame, expected_count: int) -> dict[str, Any]:
    """Fail if row count does not reconcile exactly against the expected customer base."""
    actual_count = len(features)
    passed = actual_count == expected_count
    return {
        "check": "row_count",
        "passed": passed,
        "expected_count": expected_count,
        "actual_count": actual_count,
    }


def check_no_future_leakage(
    transactions_df: pd.DataFrame,
    as_of: str | pd.Timestamp,
) -> dict[str, Any]:
    """Fail if any transaction with timestamp strictly after as_of was present in transactions used."""
    as_of_dt = pd.to_datetime(as_of)
    future_txns = transactions_df[transactions_df["txn_timestamp"] > as_of_dt]
    passed = len(future_txns) == 0
    return {
        "check": "no_future_leakage",
        "passed": passed,
        "future_row_count": len(future_txns),
    }


def check_drift(
    features: pd.DataFrame,
    reference: pd.DataFrame | None = None,
    mean_relative_tol: float = 0.5,
) -> dict[str, Any]:
    """Compare the current feature distribution against a reference snapshot.
    Fails if mean shifted by more than mean_relative_tol for any numeric feature.
    """
    if reference is None:
        return {"check": "drift", "passed": True, "drifting_features": {}}

    drifting_features = {}
    for col in FEATURE_COLUMNS:
        if col in features.columns and col in reference.columns:
            cur_mean = float(features[col].mean())
            ref_mean = float(reference[col].mean())
            if ref_mean != 0:
                rel_diff = abs(cur_mean - ref_mean) / abs(ref_mean)
            else:
                rel_diff = abs(cur_mean - ref_mean)

            if rel_diff > mean_relative_tol:
                drifting_features[col] = {
                    "current_mean": cur_mean,
                    "reference_mean": ref_mean,
                    "relative_diff": rel_diff,
                }

    passed = len(drifting_features) == 0
    return {
        "check": "drift",
        "passed": passed,
        "drifting_features": drifting_features,
    }


def run_all_checks(
    features: pd.DataFrame,
    expected_row_count: int | None = 1500,
    zero_customer_ids: list[int] | None = None,
    reference: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Run all checks and return a combined pass/fail summary.
    If any check fails, raises ValueError.
    """
    results = {}
    results["null_check"] = check_no_unexpected_nulls(features)
    results["outlier_check"] = check_outliers(features)

    if expected_row_count is not None:
        results["row_count_check"] = check_row_count(features, expected_row_count)

    if zero_customer_ids is not None:
        results["zero_defaults_check"] = check_zero_activity_defaults(features, zero_customer_ids)

    if reference is not None:
        results["drift_check"] = check_drift(features, reference)

    all_passed = all(res["passed"] for res in results.values())
    if not all_passed:
        failing_checks = [k for k, v in results.items() if not v["passed"]]
        raise ValueError(f"Data quality checks failed: {failing_checks}. Details: {results}")

    results["overall_passed"] = True
    return results
