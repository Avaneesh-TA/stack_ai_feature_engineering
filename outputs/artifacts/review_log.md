# review_log.md — Feature Engineering Review and Audit Log

This document records the stages, reviews, audit conclusions, and verification results across the development of the customer churn feature engineering pipeline.

---

## 1. Stage 0: Domain & Data Inspection Review

- **Inspected Data Sources**:
  - `data/customers.csv`: 1,500 customer records, `signup_date` spanning 2024-02-15 to 2026-07-01.
  - `data/transactions.db`: 11,742 transaction events across 1,419 distinct customers.
  - `data/transactions_monthly_agg.parquet`: 8,086 rows across 1,409 distinct customers.
- **Identified Critical Edge Cases**:
  - Exactly 81 customers have zero transactions in `transactions.db` (and 91 in `transactions_monthly_agg.parquet`). 100% of zero-transaction customers are churned. Standard joins yield `NaN` without explicit defaults.
  - Returns are stored with positive amounts; returned events are indicated solely by `is_returned = 1`.
  - The monthly aggregate stops at 2026-06-01, whereas raw transactions continue through 2026-07-31.
  - Evaluating recency or windowed frequency as of `2026-08-01` produces 100% label leakage due to the definition of churn over the trailing ~90 days.

---

## 2. Stage 1: Pipeline Implementation & Verification

- **Pure Ingestion (`features/ingest.py`)**:
  - Validated clean typing and schema conversion across CSV, SQLite, and Parquet sources.
- **Pure Transforms (`features/transforms.py`)**:
  - Candidate features: `days_since_last_txn`, `active_months_last_12m`, `spend_trajectory`, `return_rate`, `txn_count_last_Nd`, and `tenure_days`.
  - Enforced mathematical defaults for zero-activity customers: `9999.0` for recency, `0` for active months, `1.0` for spend trajectory, `0.0` for return rate, and `0` for count.
  - Handled historical `as_of` bounds cleanly on tenure days.
- **Unified Pipeline Build (`features/build.py`)**:
  - Single entry point `build_features(as_of, source_paths, customer_ids, parameters)`.
  - Identical vectorized logic executed for training and scoring; customer filtering occurs strictly at the end.
- **Quality Checks (`features/quality_checks.py`)**:
  - Validated null prevention, zero-activity default enforcement, outlier range boundaries, row count reconciliation (1,500 rows), and distribution drift checks.
- **Feature Store (`feature_store/store.py`)**:
  - Implemented metadata registry in SQLite (`feature_registry` table) + immutable Parquet value snapshots (`feature_store/values/`).
  - Supported multi-version registration without overwriting existing versions (`txn_count_last_Nd` v1/v2, `spend_trajectory` v1/v2/v3).

---

## 3. Stage 2: Script Execution Verification

All runner scripts were executed and validated end-to-end:
1. `scripts/build_training_features.py`:
   - Successfully generated full training features as of `2026-05-03` (and supports `2026-08-01`).
   - Passed all data quality assertions.
   - Populated `feature_store/registry.db` and registered snapshots for all candidate features and designated versions.
2. `scripts/score_customer.py`:
   - Successfully scored single and multiple customers (e.g. customer 42 and customer 1) using the shared `build_features` pipeline.
3. `scripts/compare_feature_versions.py`:
   - Successfully computed distribution shifts, quantiles, and Spearman rank correlations across feature versions and produced `VERSION_COMPARISON.md`.

---

## 4. Stage 3: Test Suite Audit

Ran `python -m pytest`:
- **Total Tests**: 20 collected
- **Passed**: 20 (100%)
- **Test Modules**:
  - `tests/test_feature_store.py`: 3 passed
  - `tests/test_parity.py`: 5 passed
  - `tests/test_quality_checks.py`: 6 passed
  - `tests/test_transforms.py`: 6 passed
