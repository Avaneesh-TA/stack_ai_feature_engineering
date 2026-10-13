"""
The parity test that matters most for this pipeline: build features for the same
customer via the "training" path (historical as-of date, batch of many customers) and
via the "scoring" path (single customer, same as-of date), and assert the resulting
feature values are identical.
"""

import pandas as pd
import numpy as np
import pytest

from features.build import build_features


@pytest.mark.parametrize("customer_id", [2, 42, 81, 100, 500])
def test_training_and_scoring_paths_agree_for_same_customer(customer_id: int):
    as_of = "2026-05-03"

    # Batch training path (all 1500 customers)
    batch_features = build_features(as_of=as_of, customer_ids=None)

    # Scoring path for single customer
    single_features = build_features(as_of=as_of, customer_ids=[customer_id])

    assert len(single_features) == 1
    assert single_features.iloc[0]["customer_id"] == customer_id

    batch_row = batch_features[batch_features["customer_id"] == customer_id].iloc[0]
    single_row = single_features.iloc[0]

    # Verify every column matches exactly
    for col in batch_features.columns:
        val_batch = batch_row[col]
        val_single = single_row[col]
        if isinstance(val_batch, float):
            assert np.isclose(val_batch, val_single, atol=1e-5, equal_nan=True), (
                f"Mismatch on {col}: batch={val_batch}, single={val_single}"
            )
        else:
            assert val_batch == val_single, f"Mismatch on {col}: batch={val_batch}, single={val_single}"
