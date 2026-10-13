# FEATURE_LINEAGE.md — End-to-End Feature Lineage

This document establishes the end-to-end data provenance for all candidate features in the e-commerce customer churn pipeline, linking each feature from raw source columns through transformations, quality assertions, and storage in the feature store.

---

## 1. Lineage Architecture Overview

```
[Raw Data Sources]
 ├── data/customers.csv (1,500 rows)
 ├── data/transactions.db: transactions (11,742 rows)
 └── data/transactions_monthly_agg.parquet (8,086 rows)
         │
         ▼
[Pure Ingestion Layer: features/ingest.py]
 ├── load_customers()
 ├── load_transactions()
 └── load_monthly_agg()
         │
         ▼
[Feature Transforms: features/transforms.py]
 (Pure functional transformations anchored at as_of date)
         │
         ▼
[Unified Pipeline: features/build.py (build_features)]
         │
         ├───► [Quality Assurance: features/quality_checks.py]
         │        ├── check_no_unexpected_nulls
         │        ├── check_zero_activity_defaults
         │        ├── check_outliers
         │        ├── check_row_count
         │        └── check_future_leakage
         │
         └───► [Local Feature Store: feature_store/store.py]
                  ├── Registry: feature_store/registry.db (SQLite)
                  └── Snapshots: feature_store/values/<feature>__v<version>.parquet
```

---

## 2. Feature-by-Feature Lineage Matrix

| Feature Name | Version | Source Tables & Columns | Transform Function | Explicit Zero-Activity Default | Quality Checks & Bounds | Storage Snapshot |
|---|---|---|---|---|---|---|
| `days_since_last_txn` | v1 | `data/transactions.db` → `transactions.txn_timestamp` | `compute_days_since_last_txn` | `9999.0` (float) | Non-null, bounds: `[0.0, 9999.0]`, leakage check vs `as_of` | `feature_store/values/days_since_last_txn__v1.parquet` |
| `active_months_last_12m` | v1 | `data/transactions_monthly_agg.parquet` → `txn_month` | `compute_active_months_last_12m` | `0` (int) | Non-null, bounds: `[0, 12]` calendar months | `feature_store/values/active_months_last_12m__v1.parquet` |
| `spend_trajectory` | v1 | `data/transactions_monthly_agg.parquet` → `total_amount`, `txn_month` | `compute_spend_trajectory(recent_window_months=3)` | `1.0` (float) | Non-null, bounds: `[0.0, 1000.0]`, zero-baseline handled | `feature_store/values/spend_trajectory__v1.parquet` |
| `spend_trajectory` | v2 | `data/transactions_monthly_agg.parquet` → `total_amount`, `txn_month` | `compute_spend_trajectory(recent_window_months=6)` | `1.0` (float) | Non-null, bounds: `[0.0, 1000.0]` | `feature_store/values/spend_trajectory__v2.parquet` |
| `spend_trajectory` | v3 | `data/transactions_monthly_agg.parquet` → `total_amount`, `txn_month` | `compute_spend_trajectory(recent_window_months=2)` | `1.0` (float) | Non-null, bounds: `[0.0, 1000.0]` | `feature_store/values/spend_trajectory__v3.parquet` |
| `return_rate` | v1 | `data/transactions.db` → `transactions.is_returned`, `txn_timestamp` | `compute_return_rate(window_days=180)` | `0.0` (float) | Non-null, bounds: `[0.0, 1.0]`, ratio check | `feature_store/values/return_rate__v1.parquet` |
| `txn_count_last_Nd` | v1 | `data/transactions.db` → `transactions.txn_timestamp` | `compute_txn_count_last_nd(window_days=180)` | `0` (int) | Non-null, bounds: `[0, 1000]`, leakage check vs `as_of` | `feature_store/values/txn_count_last_Nd__v1.parquet` |
| `txn_count_last_Nd` | v2 | `data/transactions.db` → `transactions.txn_timestamp` | `compute_txn_count_last_nd(window_days=90)` | `0` (int) | Non-null, bounds: `[0, 1000]` | `feature_store/values/txn_count_last_Nd__v2.parquet` |
| `tenure_days` | v1 | `data/customers.csv` → `customers.signup_date` | `compute_tenure_days` | N/A (all customers have signup_date) | Non-null, bounds: `[0.0, inf)` | `feature_store/values/tenure_days__v1.parquet` |

---

## 3. Transformation Logics & Point-In-Time Guardrails

### 1. `days_since_last_txn`
- **Logic**: Filters transactions strictly to `txn_timestamp <= as_of`. Computes `(as_of - max(txn_timestamp)).total_seconds() / 86400.0`. Missing customers (those with zero transactions prior to `as_of`) are filled with `9999.0`.
- **Point-in-time guardrail**: Strict `< = as_of` filter prevents label leakage into subsequent churn observation windows.

### 2. `active_months_last_12m`
- **Logic**: Anchors window to the preceding 12 calendar months: `[as_of.to_period('M') - 11, as_of.to_period('M')]`. Filters `monthly_agg` rows with `txn_count >= 1`, groups by `customer_id`, counts unique months, and reindexes against the complete customer base filling zero-activity with `0`.
- **Point-in-time guardrail**: Partial/future months outside the trailing 12-month boundary are completely excluded.

### 3. `spend_trajectory`
- **Logic**:
  - Recent window: `[as_of.to_period('M') - W + 1, as_of.to_period('M')]`
  - Baseline window: `[as_of.to_period('M') - 2*W + 1, as_of.to_period('M') - W]`
  - Computes monthly mean spend in both windows.
  - Ratio = `recent_mean / baseline_mean`.
  - Customers with zero baseline spend or zero total activity default to `1.0` (indicating baseline parity / neutral trajectory).

### 4. `return_rate`
- **Logic**: Filters transactions in the half-open window `(as_of - window_days, as_of]`. Computes `SUM(is_returned) / COUNT(*)`. Zero-transaction customers receive default `0.0`.

### 5. `txn_count_last_Nd`
- **Logic**: Counts events in `(as_of - window_days, as_of]`. Reindexes against all customers filling missing entries with `0`.

### 6. `tenure_days`
- **Logic**: Evaluates account age as `(as_of - signup_date).days`. Clamped or evaluated at valid observation dates.

---

## 4. Train/Score Parity Lineage

```
                       build_features(as_of, customer_ids)
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
      Training Invocation                             Scoring Invocation
  build_features(as_of="2026-05-03",              build_features(as_of="2026-08-01",
                 customer_ids=None)                              customer_ids=[42])
              │                                               │
              ├─ load_customers()                             ├─ load_customers()
              ├─ load_transactions()                          ├─ load_transactions()
              ├─ load_monthly_agg()                           ├─ load_monthly_agg()
              │                                               │
              ├─ compute_days_since_last_txn()                ├─ compute_days_since_last_txn()
              ├─ compute_active_months_last_12m()             ├─ compute_active_months_last_12m()
              ├─ compute_spend_trajectory()                   ├─ compute_spend_trajectory()
              ├─ compute_return_rate()                        ├─ compute_return_rate()
              ├─ compute_txn_count_last_nd()                  ├─ compute_txn_count_last_nd()
              └─ compute_tenure_days()                        └─ compute_tenure_days()
                      │                                               │
               [All 1,500 rows]                                [All 1,500 rows]
                      │                                               │
                      ▼                                               ▼
            Filter: customer_ids=None                       Filter: customer_ids=[42]
                      │                                               │
                      ▼                                               ▼
             Return 1,500 rows                                 Return 1 row
```

**Key Parity Guarantee**: There are no conditional branches within the mathematical transforms. Training and scoring execute the exact same vectorized computation. Filtering is performed strictly at the final step.
