"""
Feed each check in features/quality_checks.py a deliberately bad input (an injected
null, an out-of-range amount, a shifted distribution) and confirm it fires; feed it
clean input and confirm it doesn't false-positive.
"""

import pandas as pd
import numpy as np
import pytest

from features import quality_checks
from features.build import build_features


@pytest.fixture
def clean_features():
    return build_features(as_of="2026-05-03")


def test_checks_do_not_false_positive_on_clean_input(clean_features):
    results = quality_checks.run_all_checks(clean_features, expected_row_count=1500)
    assert results["overall_passed"] is True
    assert results["null_check"]["passed"] is True
    assert results["outlier_check"]["passed"] is True
    assert results["row_count_check"]["passed"] is True


def test_null_check_fires_on_injected_null(clean_features):
    corrupted = clean_features.copy()
    corrupted.loc[0, "days_since_last_txn"] = np.nan

    res = quality_checks.check_no_unexpected_nulls(corrupted)
    assert res["passed"] is False
    assert "days_since_last_txn" in res["failing_features"]

    with pytest.raises(ValueError, match="Data quality checks failed"):
        quality_checks.run_all_checks(corrupted)


def test_outlier_check_fires_on_out_of_range_value(clean_features):
    # Test return rate > 1.0
    bad_ret = clean_features.copy()
    bad_ret.loc[0, "return_rate"] = 1.5
    res = quality_checks.check_outliers(bad_ret)
    assert res["passed"] is False
    assert "return_rate" in res["failing_features"]

    # Test negative txn count
    bad_cnt = clean_features.copy()
    bad_cnt.loc[0, "txn_count_last_Nd"] = -5
    res = quality_checks.check_outliers(bad_cnt)
    assert res["passed"] is False
    assert "txn_count_last_Nd" in res["failing_features"]

    # Test negative tenure
    bad_tenure = clean_features.copy()
    bad_tenure.loc[0, "tenure_days"] = -10.0
    res = quality_checks.check_outliers(bad_tenure)
    assert res["passed"] is False
    assert "tenure_days" in res["failing_features"]


def test_drift_check_fires_on_shifted_distribution(clean_features):
    shifted = clean_features.copy()
    # Drastically shift spend_trajectory distribution
    shifted["spend_trajectory"] = shifted["spend_trajectory"] * 10.0

    res = quality_checks.check_drift(shifted, reference=clean_features, mean_relative_tol=0.2)
    assert res["passed"] is False
    assert "spend_trajectory" in res["drifting_features"]


def test_row_count_check_fires_on_dropped_rows(clean_features):
    dropped = clean_features.iloc[:1400].copy()
    res = quality_checks.check_row_count(dropped, expected_count=1500)
    assert res["passed"] is False
    assert res["actual_count"] == 1400


def test_zero_defaults_check_fires_on_nan_default(clean_features):
    # Pass customer 1 as a zero customer, but corrupt their default to NaN
    corrupted = clean_features.copy()
    corrupted.loc[corrupted["customer_id"] == 1, "days_since_last_txn"] = np.nan
    res = quality_checks.check_zero_activity_defaults(corrupted, zero_customer_ids=[1])
    assert res["passed"] is False
    assert 1 in res["failing_rows"]
