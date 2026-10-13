# PARITY_CHECK.md — Train/Score Parity Audit & Mutation Verification

This document verifies strict mathematical and operational parity between the batch training pipeline and single-instance scoring invocations.

---

## 1. Architectural Parity Contract

To eliminate online-offline skew, train/score parity is enforced at the architectural level:
- **Single Source of Truth**: All feature transformations are declared in `features/transforms.py` as pure mathematical functions.
- **Unified Pipeline Entry Point**: Both `scripts/build_training_features.py` (batch generation across all 1,500 customers) and `scripts/score_customer.py` (single or multi-customer inference) invoke the identical entry point:
  ```python
  features/build.py: build_features(as_of, source_paths=None, customer_ids=None, parameters=None)
  ```
- **Strict Vectorized Parity**: No branching exists based on whether execution is training or scoring. All customer features are derived from the exact same vectorized calculations. The `customer_ids` parameter acts strictly as a post-computation slice at the final line of `build_features()`.

---

## 2. Test Verification Matrix

Automated parity tests located in `tests/test_parity.py` confirm exact equality between training and scoring evaluations:

| Test Name | Scenario Checked | Tolerance | Result |
|---|---|---|---|
| `test_parity_single_customer` | Scored single customer (#42) vs row 42 in 1,500-customer batch | Exact `0.0` tolerance (assert_series_equal) | **PASSED** |
| `test_parity_zero_activity_customer` | Scored zero-transaction customer (#1) vs batch row 1 | Exact match on all sentinels (`9999.0`, `1.0`, `0.0`, `0`) | **PASSED** |
| `test_parity_multiple_customers` | Scored subset `[10, 42, 100, 500]` vs batch sliced rows | Exact match across all columns and rows | **PASSED** |
| `test_parity_nonexistent_customer_raises` | Scoring non-existent customer `99999` raises `ValueError` | Expected `ValueError` caught | **PASSED** |
| `test_parity_mutation_detection` | Injected scalar drift into single-scoring branch | Verified that disparity is detected | **PASSED** |

---

## 3. Mutation Testing Verification

To confirm that parity validation is sensitive to deviations, mutation testing was conducted:
1. **Mutation Injected**: A synthetic drift of `+1.0` was introduced into `days_since_last_txn` exclusively on scoring calls.
2. **Detection**: `test_parity_mutation_detection` immediately caught the discrepancy with assertion failure:
   ```
   AssertionError: Series are different: Series values are different (100.0%)
   [left]:  17.759604
   [right]: 16.759604
   ```
3. **Restoration**: The baseline unified code path was validated clean with all 20 tests in the test suite passing.
