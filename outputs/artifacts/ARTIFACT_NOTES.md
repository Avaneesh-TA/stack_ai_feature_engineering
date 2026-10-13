# ARTIFACT_NOTES.md — Pipeline Data & Engineering Audit Notes

This document records genuine data discrepancies, architectural design choices, edge-case resolutions, and audit notes discovered during inspection of the raw data files and execution of the feature pipeline.

---

## 1. Source Data Anomalies & Discrepancies

Per instructions, **no raw data files were edited or modified**. All issues are handled defensively in the code layer.

### 1.1 July 2026 Monthly Aggregate Truncation
- **Observation**: `data/transactions.db` contains transactions through **2026-07-31**, with 344 transactions in July 2026 across hundreds of customers. However, `data/transactions_monthly_agg.parquet` contains records only through **2026-06-01** (June 2026), completely omitting or only having partial/missing customer representation for July 2026.
- **Impact**: Any feature relying on `transactions_monthly_agg.parquet` that attempts to evaluate calendar month 2026-07 will experience an artificial 0-spend cliff if not anchored to the last complete calendar month (2026-06).
- **Engineering Resolution**: Monthly aggregate windowing logic explicitly aligns with completed calendar months or defaults missing entries safely via reindexing.

### 1.2 Zero-Transaction Inactivity (81 Customers)
- **Observation**: Exactly 81 customers in `customers.csv` have zero records in `transactions.db`. Furthermore, 91 customers have zero records in `transactions_monthly_agg.parquet`.
- **Finding**: 100% of the zero-activity customers in `customers.csv` churned (`churned = 1`).
- **Impact**: Standard pandas merges (`left_join`) produce `NaN` across recency, frequency, and monetary features for these customers. Downstream ML models or assertions fail if NaNs are unhandled.
- **Engineering Resolution**: Every transformation explicitly enforces default sentinels:
  - `days_since_last_txn`: `9999.0` (sentinel for no prior transaction)
  - `active_months_last_12m`: `0`
  - `spend_trajectory`: `1.0` (neutral trajectory)
  - `return_rate`: `0.0`
  - `txn_count_last_Nd`: `0`

### 1.3 Returns Accounting (Positive Dollar Values)
- **Observation**: In `data/transactions.db`, returned transactions (`is_returned = 1`) store positive `amount` values (min $3.00, mean $49.72), rather than negative balances.
- **Impact**: A naive `SUM(amount)` represents gross volume rather than net revenue.
- **Engineering Resolution**: Feature transforms distinguish between return rate (`SUM(is_returned) / COUNT(*)`) and transaction volume, maintaining clear semantic separation.

---

## 2. Point-in-Time Correctness & Churn Label Leakage

### 2.1 The 2026-08-01 Observation Cliff
- **Finding**: The dataset defines customer churn based on transaction inactivity over the trailing ~90 days leading up to 2026-08-01. Consequently, computing `days_since_last_txn` or `txn_count_last_90d` as of `2026-08-01` creates a 100% deterministic separator of the churn label (i.e. every churned customer has `txn_count_last_90d == 0` and `days_since_last_txn > 90`).
- **Engineering Resolution**:
  - The pipeline supports an explicit `as_of` anchor date.
  - To prevent label leakage during training, feature generation can be anchored to `2026-05-03` (the start of the churn observation window) or evaluated before the churn observation window.
  - Scoring requests at inference time pass `as_of = "2026-08-01"` to score current customer health without leakage.

### 2.2 Customer Signup Dates vs Historical `as_of`
- **Finding**: In `customers.csv`, customer signup dates span up to `2026-07-01`. Evaluating historical training features at `as_of = "2026-05-03"` reveals 100 customers who had not yet signed up as of May 3, 2026.
- **Resolution**: Quality check outliers for `tenure_days` and transformations accommodate population as-of constraints, ensuring clean evaluation across both training and inference dates.

---

## 3. Train/Score Parity Implementation

- **Single Shared Function**: Both `scripts/build_training_features.py` and `scripts/score_customer.py` invoke `features/build.py:build_features()`.
- **Vectorized Parity**: No branching exists inside the transformation functions. The single scoring path evaluates the transforms across the inputs and performs a final index filter (`features_df[features_df["customer_id"].isin(customer_ids)]`).
- **Verification**: Mutation and unit tests in `tests/test_parity.py` confirm identical floating point outputs across both pathways.

---

## 4. Local Feature Store Architecture

- **Engine**: SQLite metadata registry (`feature_store/registry.db`) + versioned Apache Parquet snapshots (`feature_store/values/<feature>__v<version>.parquet`).
- **Immutability**: Re-registering the same feature name appends a new version number (`v1` → `v2` → `v3`). Previous versions are never overwritten or mutated.
- **Atomic Pointer**: The `is_latest` boolean flag in `feature_registry` updates atomically upon insertion of a new version.
