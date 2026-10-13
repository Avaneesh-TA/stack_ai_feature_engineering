# feature_spec.md — Churn Feature Pipeline
## SKELETON — fill this in

## Candidate features

<<One block per feature — add/remove freely. At minimum per feature, per skill.md's Domain
Context: name, source(s), computation, an explicit zero-activity default (never null/NaN),
and a rationale naming a specific customer behavior distinct from a plausible confound.>>
- **Feature 1**: `days_since_last_txn`
- **Source:** `transactions.db: txn_timestamp` (row-level — the monthly aggregate cannot express an exact recency window)
- **Computation:** `(as_of - max(txn_timestamp)).days` for customers with ≥1 txn.
- **Zero-activity default:** 9999 days
- **Rationale:** longer time since last activity is a direct churn signal. 🚨 **BUT in this dataset, as of 2026-08-01 this feature is a perfect separator of the label (§6.4) — it is  the label's definition, not a predictor. As a *candidate* it is the canonical recency feature; as *built feature* it leaks unless `as_of` is moved to the churn-window start.(Training as_of fixed at 2026-05-03 to prevent leakage).

- **Feature 2**: `active_months_last_12m`
- **Source:** `transactions_monthly_agg: txn_month` (naturally suited to the aggregate; the
  row-level table could also derive it but the aggregate is the convenient source)
- **Computation:** count of distinct `txn_month` values in the last 12 complete months
  (through 2026-06) where the customer had ≥1 txn. Reindex over the full customer base.
- **Zero-activity default:** `0` — never NaN.
- **Rationale:** breadth of activity over a longer window captures engagement consistency —
  a customer active in many of the last 12 months has a stable habit. This is **not** a
  restatement of the label: a churned customer (last txn 2026-04) can still have had 9 active
  months in the trailing year, and a non-churned customer can have had only 3. It separates
  "always-sparse but present" from "was-broadly-engaged-then-lapsed."

- **FEATURE 3**: `spend_trajectory` (recent vs own baseline)
- **Source:** `transactions_monthly_agg: total_amount` (calendar-month granularity is fine for
  a month-ratio); or `transactions.db` for a rolling-window ratio. Either works; the aggregate
  is cheaper.
- **Computation:** ratio (or difference) of recent mean monthly spend to the customer's own
  prior baseline monthly spend — e.g. mean of the 3 most recent *complete* months ÷ mean of
  the prior 3 complete months, computed **before the churn window**. Define a floor to avoid
  divide-by-zero.
- **Zero-activity default:** `1.0` (no change) or `0.0` per spec — never NaN; handle
  zero-baseline explicitly.
- **Rationale:** a decline in spend **relative to the customer's own baseline** signals
  disengagement, **distinct from a customer who has always spent little** (the canonical
  "real vs filler" rationale: it names a behavior — a drop from their own norm — and
  distinguishes it from the confound of a perpetually-low spender). This is the most defensible
  family in this dataset because it is not a restatement of the label.

- **FEATURE 4**: `return_rate` (windowed)
- **Source:** `transactions.db: is_returned` (count-based; the monthly aggregate has
  `return_count` and `txn_count`, so a calendar-month version is also available)
- **Computation:** `SUM(is_returned) / COUNT(*)` over a window **ending before the churn
  window** (otherwise a churned customer trivially has 0 returns in the churn window = leakage
  by another name).
- **Zero-activity default:** `0.0` — never NaN.
- **Rationale:** a rising share of returns signals unmet expectations / dissatisfaction that
  can precede churn, **distinct from low spend** — a customer can spend normally and still be
  trending toward churn if their return share is climbing. Overall return rate is ~5% with
  modest category variation (4.5%–5.7%).

- **FEATURE 5**: `txn_count_last_Nd` (windowed frequency)
- **Source:** `transactions.db: txn_timestamp` for short windows (the monthly aggregate can't
  align a rolling N-day window to calendar months); `transactions_monthly_agg: txn_count` is
  fine for calendar-month-aligned longer windows.
- **Computation:** count of `txn_timestamp` in `(as_of - N days, as_of]`.
- **Zero-activity default:** `0` (an integer count — never NaN).
- **Rationale:** transaction frequency in a window is a core engagement signal. 🚨 For
  N ≤ 90 and `as_of = 2026-08-01`, this is 0 for all churned customers — leakage (§6.4). For
  larger N it partially overlaps the churn window.

- **feature 6**: `tenure_days`
- **Source:** `customers.csv: signup_date`
- **Computation:** `(as_of - signup_date).days`
- **Zero-activity default:** N/A (every customer has a `signup_date`); always defined.
- **Rationale:** newer customers have not yet formed a purchasing habit and churn at higher rates; this is distinct from inactivity — a new customer can be highly active and still be at structural churn risk because the habit is unproven. ✅
- **Leakage:** none (signup is before any churn window).

- deleted several proposed features for example region name was deleted because its not like all customers from one region would churn more or less.
- i have included tenure days feature because of no leakage risk and it is a profile based feature from customers.csv file.

**Train/score parity design**

- **Shared code path:** every feature is computed through one function —
  `build_features(as_of, source_paths=None, customer_ids=None)` in features/build.py.
  Both scripts/build_training_features.py and scripts/score_customer.py call it;
  neither contains any feature logic of its own. No transform branches on
  "is this the training or scoring call."

- **The only allowed difference between the two call sites — the `customer_ids` argument:**
  - Training: build_features(as_of="2026-05-03", customer_ids=None)
    → one row per customer in the full base.
  - Scoring:   build_features(as_of=<score date>, customer_ids=[42])
    → one row for customer 42 only.
  The sole conditional in the code path is "if customer_ids is None, use all
  customers; else filter to that list" — applied at the end, after every transform
  has already run identically.

- **How `as_of` is threaded:** `as_of` is a required parameter of build_features
  (no default). It is forwarded explicitly to every transform as
  `transform(df, as_of=as_of)` and used only to anchor each window boundary
  (as_of - 90d, as_of - 12m, etc.). No transform hardcodes or defaults `as_of`
  internally, so a caller can never silently get a different anchor than the build
  intended.

- **Parity guarantee:** for any fixed (customer_id, as_of) pair, the returned row is
  identical whether the caller passed customer_ids=None or customer_ids=[that id].
  test_parity.py asserts this by calling both ways with the same as_of and
  comparing the overlapping customer's row.


- **Features versioned**: txn_count_last_Nd, spend_trajectory  (2 distinct features)

- Per versioned feature:

  **Feature**: txn_count_last_Nd
  **Parameter**: window_days
  **Value per version**: v1 = 180, v2 = 90
  **Reason each version differs**:
    - v1→v2: shortened from 180d to 90d because churn-window analysis
      (data_dictionary §6.4) showed trailing-≤90d behavior carries the
      churn signal; the full-year window counted year-old activity that no
      longer reflects current purchase intent, diluting the signal for
      customers active a year ago but disengaged recently. The value changes
      materially for those customers, so this is a real bump, not a rename.

  **Feature**: spend_trajectory
  **Parameter**: recent_window_months  (baseline window = same length, by design)
  **Value per version**: v1 = 3, v2 = 6, v3 = 2
  **Reason each version differs**:
    - v1→v2: widened from 3 to 6 months because median transaction frequency
      is ~7 txns/year, so a 3-month window held 0–1 txns for many customers
      and made the recent-vs-baseline ratio numerically unstable; 6 months
      gives a stable baseline.
    - v2→v3: narrowed back to 2 months because the 6-month window averaged
      away exactly the recent-decline signal the feature exists to detect —
      a customer dropping in the last 2 months was smoothed into their
      6-month average; 2 months isolates that drop. Each version changes
      the value materially for customers whose spending isn't flat.

- **What forces a version bump vs. not**: a real bump changes a parameter, source, or computation so the values differ materially for some customers with a stated business reason; a renamed column or reformatted description with no computational change is cosmetic and is NOT a version bump.

- **What a lineage entry must let someone reconstruct**: enough to recompute
  the feature by hand from raw data without reading any code — the exact source file/table + columns, the transform steps, the window boundaries anchored to as_of, and every parameter value for that version.

## Multi-source judgment calls

<<At minimum, per skill.md's Domain Context: per feature that could come from either source,
which was chosen and why.>>
- **Feature**: txn_count_last_90d — **Source chosen**: transactions.db —
  **Why**: rolling 90-day window (anchored to as_of, not month-aligned) can't be expressed at month grain

- **Feature**: active_months_last_12m — **Source chosen**:
  transactions_monthly_agg.parquet — **Why**: the feature IS a count of active
  calendar months — the aggregate is its natural grain, and only complete
  months through 2026-06 are counted.

- **Feature**: spend_trajectory — **Source chosen**: transactions_monthly_agg.parquet
  — **Why**: a ratio of recent-month to baseline-month spend is month-grained by
  design; using complete months avoids the 2026-07 partial-month contamination
  entirely.

- **Feature**: return_rate_last_6m — **Source chosen**: transactions.db —
  **Why**: although the aggregate has return_count and txn_count, a 6-month rolling window anchored to  as_of isn't month-aligned; row-level avoids the grain mismatch.

## Data-quality checks

Run after build_features() produces the DataFrame, before anything is written
to the feature store. A failing check raises (non-zero exit) — it never just
logs and continues.

- **Check**: no unexpected nulls in any feature column — **Catches**: a
  groupby/reindex that drops the 81 zero-transaction customers (data_dictionary
  §6.1) instead of applying their stated default — **On failure**: raise.

- **Check**: zero-activity customers carry the stated default, not NaN —
  **Catches**: the off-by-one where a default is declared in the spec but a
  fillna is skipped, leaving the 81 zero-txn customers with silent NaN on
  recency/frequency/monetary features — **On failure**: raise.

- **Check**: monetary/aggregate features within sane bounds — **Catches**: a
  duplicate-row join inflating spend (values exceed the max observed monthly
  total of $1753, so a windowed spend > ~$50,000 signals a join/unit error),
  and a return_rate outside [0,1] (a divide-by-zero or count mismatch) —
  **On failure**: raise.

- **Check**: row count reconciles against the customer base — **Catches**:
  a join dropping or duplicating customers (training output ≠ 1500 rows;
  scoring output ≠ number of requested customer_ids) — **On failure**: raise.

- **Check**: no transaction used in any feature has txn_timestamp after as_of
  — **Catches**: a window that silently reaches past its anchor into the
  churn/performance window, i.e. label leakage (data_dictionary §6.4) —
  **On failure**: raise.

