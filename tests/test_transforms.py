"""
Pure transform tests in isolation for features/transforms.py.
Covers for each transform:
- Normal case
- Zero-activity case (asserts spec's explicit default, never NaN)
- Single-record case
- Boundary case
"""

import pandas as pd
import numpy as np
import pytest

from features import transforms


@pytest.fixture
def sample_customers():
    return pd.DataFrame(
        {
            "customer_id": [1, 2, 3, 4],
            "signup_date": pd.to_datetime(["2024-01-01", "2024-06-01", "2025-01-01", "2026-01-01"]),
            "acquisition_channel": ["organic", "social", "paid_search", "referral"],
            "region": ["east", "west", "north", "south"],
            "churned": [0, 0, 1, 1],
        }
    )


@pytest.fixture
def sample_transactions():
    return pd.DataFrame(
        {
            "customer_id": [1, 1, 2, 3],
            "txn_timestamp": pd.to_datetime(
                [
                    "2026-04-01 12:00:00",
                    "2026-05-01 10:00:00",
                    "2026-02-02 08:00:00",  # Single record for customer 2 (90 days before 2026-05-03)
                    "2026-01-01 12:00:00",
                ]
            ),
            "category": ["home", "apparel", "grocery", "electronics"],
            "channel": ["web", "mobile_app", "store", "web"],
            "amount": [50.0, 100.0, 30.0, 80.0],
            "is_returned": [0, 1, 0, 0],
        }
    )


@pytest.fixture
def sample_monthly_agg():
    return pd.DataFrame(
        {
            "customer_id": [1, 1, 1, 2],
            "txn_month": pd.to_datetime(["2026-02-01", "2026-03-01", "2026-04-01", "2026-02-01"]),
            "txn_count": [2, 1, 3, 1],
            "total_amount": [100.0, 50.0, 150.0, 30.0],
            "return_count": [0, 1, 0, 0],
        }
    )


def test_days_since_last_txn(sample_customers, sample_transactions):
    as_of = "2026-05-03"
    res = transforms.compute_days_since_last_txn(sample_customers, sample_transactions, as_of)

    # Customer 1: last txn 2026-05-01 10:00:00 -> ~1.58 days
    assert res.loc[1] < 2.0
    # Customer 4: zero-activity -> explicit default 9999.0
    assert res.loc[4] == 9999.0
    assert not np.isnan(res.loc[4])
    # Customer 2: single record on 2026-02-02 -> ~90 days
    assert 89.0 < res.loc[2] < 91.0


def test_active_months_last_12m(sample_customers, sample_monthly_agg):
    as_of = "2026-05-03"
    res = transforms.compute_active_months_last_12m(sample_customers, sample_monthly_agg, as_of)

    # Customer 1: 3 active months (Feb, Mar, Apr)
    assert res.loc[1] == 3
    # Customer 2: 1 active month
    assert res.loc[2] == 1
    # Customer 4: zero activity -> 0
    assert res.loc[4] == 0
    assert not np.isnan(res.loc[4])


def test_spend_trajectory(sample_customers, sample_monthly_agg):
    as_of = "2026-05-03"
    # Customer 1:
    # Recent 3 months: Feb, Mar, Apr 2026 -> spend = 100 + 50 + 150 = 300; mean = 100
    # Baseline 3 months: Nov 2025, Dec 2025, Jan 2026 -> 0 spend
    # Zero baseline defaults to 1.0
    res_v1 = transforms.compute_spend_trajectory(sample_customers, sample_monthly_agg, as_of, recent_window_months=3)
    assert res_v1.loc[1] == 1.0
    assert res_v1.loc[4] == 1.0  # Zero activity customer defaults to 1.0
    assert not np.isnan(res_v1.loc[4])


def test_return_rate(sample_customers, sample_transactions):
    as_of = "2026-05-03"
    res = transforms.compute_return_rate(sample_customers, sample_transactions, as_of, window_days=180)

    # Customer 1: 2 txns in window, 1 returned -> 0.5
    assert res.loc[1] == 0.5
    # Customer 2: 1 txn, 0 returned -> 0.0
    assert res.loc[2] == 0.0
    # Customer 4: 0 txns -> default 0.0
    assert res.loc[4] == 0.0
    assert not np.isnan(res.loc[4])


def test_txn_count_last_nd_and_boundary(sample_customers, sample_transactions):
    as_of = "2026-05-03"
    # Customer 2 txn is at 2026-02-02 08:00:00 (approx 90 days before 2026-05-03)
    res_90d = transforms.compute_txn_count_last_nd(sample_customers, sample_transactions, as_of, window_days=90)
    res_180d = transforms.compute_txn_count_last_nd(sample_customers, sample_transactions, as_of, window_days=180)

    # In 180d, Customer 1 has 2 txns, Customer 2 has 1, Customer 3 has 1
    assert res_180d.loc[1] == 2
    assert res_180d.loc[2] == 1
    assert res_180d.loc[3] == 1
    assert res_180d.loc[4] == 0  # Zero-activity default
    assert not np.isnan(res_180d.loc[4])


def test_tenure_days(sample_customers):
    as_of = "2026-05-03"
    res = transforms.compute_tenure_days(sample_customers, as_of)

    # Customer 1 signup 2024-01-01 -> > 800 days
    assert res.loc[1] > 800
    # All customers non-null
    assert res.isna().sum() == 0
