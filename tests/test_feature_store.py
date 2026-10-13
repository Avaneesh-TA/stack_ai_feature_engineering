"""
Feature store tests for feature_store/store.py:
- Proves every version of every feature_spec.md-designated versioned feature is stored and independently retrievable.
- Proves is_latest correctly points to the highest version and not an earlier one.
- Proves list_versions returns every version with distinct parquet_path values that all actually exist on disk.
"""

from pathlib import Path
import pytest
import pandas as pd
import numpy as np

from feature_store import store


@pytest.fixture
def temp_store(tmp_path):
    db_path = str(tmp_path / "test_registry.db").replace("\\", "/")
    values_dir = str(tmp_path / "values").replace("\\", "/")
    return db_path, values_dir


def test_register_and_retrieve_all_versions_of_a_versioned_feature(temp_store):
    db_path, values_dir = temp_store

    # Test txn_count_last_Nd with 2 versions
    df_v1 = pd.DataFrame({"customer_id": [1, 2], "txn_count_last_Nd": [5, 0], "as_of_date": ["2026-05-03"] * 2})
    df_v2 = pd.DataFrame({"customer_id": [1, 2], "txn_count_last_Nd": [2, 0], "as_of_date": ["2026-05-03"] * 2})

    v1 = store.register_version(
        "txn_count_last_Nd", df_v1, "v1 desc", "source", "transform", "rationale", {"window_days": 180},
        db_path=db_path, values_dir=values_dir
    )
    assert v1 == 1

    v2 = store.register_version(
        "txn_count_last_Nd", df_v2, "v2 desc", "source", "transform", "rationale", {"window_days": 90},
        db_path=db_path, values_dir=values_dir
    )
    assert v2 == 2

    # Independently retrievable
    ret_v1 = store.get_version("txn_count_last_Nd", 1, db_path=db_path)
    ret_v2 = store.get_version("txn_count_last_Nd", 2, db_path=db_path)

    assert ret_v1.loc[0, "txn_count_last_Nd"] == 5
    assert ret_v2.loc[0, "txn_count_last_Nd"] == 2


def test_is_latest_points_to_highest_version_not_an_earlier_one(temp_store):
    db_path, values_dir = temp_store

    # Test spend_trajectory with 3 versions
    for v_num, win_months in [(1, 3), (2, 6), (3, 2)]:
        df = pd.DataFrame({"customer_id": [1], "spend_trajectory": [float(win_months)], "as_of_date": ["2026-05-03"]})
        store.register_version(
            "spend_trajectory", df, f"v{v_num}", "source", "transform", f"rationale {v_num}",
            {"recent_window_months": win_months}, db_path=db_path, values_dir=values_dir
        )

    latest_df = store.get_latest("spend_trajectory", db_path=db_path)
    # Latest should be v3, where spend_trajectory value is 2.0
    assert latest_df.loc[0, "spend_trajectory"] == 2.0


def test_list_versions_returns_distinct_parquet_paths_that_exist(temp_store):
    db_path, values_dir = temp_store

    for v_num in [1, 2, 3]:
        df = pd.DataFrame({"customer_id": [1], "spend_trajectory": [1.0], "as_of_date": ["2026-05-03"]})
        store.register_version(
            "spend_trajectory", df, f"v{v_num}", "src", "tf", "rat", {},
            db_path=db_path, values_dir=values_dir
        )

    versions_df = store.list_versions("spend_trajectory", db_path=db_path)
    assert len(versions_df) == 3

    # Check distinct paths
    paths = versions_df["parquet_path"].tolist()
    assert len(set(paths)) == 3

    # Check every path actually exists on disk
    for p in paths:
        assert Path(p).exists()

    # Check is_latest flag: only the highest version (v3) has is_latest == 1
    v3_row = versions_df[versions_df["version"] == 3].iloc[0]
    v2_row = versions_df[versions_df["version"] == 2].iloc[0]
    v1_row = versions_df[versions_df["version"] == 1].iloc[0]

    assert v3_row["is_latest"] == 1
    assert v2_row["is_latest"] == 0
    assert v1_row["is_latest"] == 0
