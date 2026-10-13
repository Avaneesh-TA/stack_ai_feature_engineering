"""
Versioned output feature schema: the authoritative list of every feature this pipeline
produces, with dtype, nullability, source(s), and feature-set version.

This is generated/maintained from `feature_spec.md`, and is consumed by
`FEATURE_LINEAGE.md` generation and by the feature store registration step.
"""

from dataclasses import dataclass


@dataclass
class FeatureSpec:
    name: str
    dtype: str
    nullable: bool
    source: str
    feature_set_version: str
    description: str
    transform_summary: str
    business_rationale: str
    parameters: dict


FEATURE_SCHEMA: list[FeatureSpec] = [
    FeatureSpec(
        name="days_since_last_txn",
        dtype="float64",
        nullable=False,
        source="data/transactions.db:transactions.txn_timestamp",
        feature_set_version="v1",
        description="Days between the as-of date and the customer's most recent transaction.",
        transform_summary="(as_of - max(txn_timestamp)).days for transactions <= as_of. Reindex over all customers, filling missing with 9999.0.",
        business_rationale="Longer time since last activity indicates customer disengagement and churn risk.",
        parameters={},
    ),
    FeatureSpec(
        name="active_months_last_12m",
        dtype="int64",
        nullable=False,
        source="data/transactions_monthly_agg.parquet:transactions_monthly_agg.txn_month,txn_count",
        feature_set_version="v1",
        description="Number of distinct active calendar months in the 12 complete months prior to as_of.",
        transform_summary="Count distinct txn_month in [as_of_month_start - 12m, as_of_month_start) where txn_count >= 1. Reindex over all customers, filling missing with 0.",
        business_rationale="Breadth of purchasing activity across months measures habit and engagement consistency.",
        parameters={"window_months": 12},
    ),
    FeatureSpec(
        name="spend_trajectory",
        dtype="float64",
        nullable=False,
        source="data/transactions_monthly_agg.parquet:transactions_monthly_agg.total_amount,txn_month",
        feature_set_version="v2",  # Default latest version
        description="Ratio of recent average monthly spend to baseline average monthly spend.",
        transform_summary="recent_mean_spend / baseline_mean_spend over recent_window_months (and preceding equal baseline window). Zero baseline or zero activity defaults to 1.0.",
        business_rationale="A decline in spend relative to a customer's own baseline signals churn risk, distinct from perpetually low spenders.",
        parameters={"recent_window_months": 6},
    ),
    FeatureSpec(
        name="return_rate",
        dtype="float64",
        nullable=False,
        source="data/transactions.db:transactions.is_returned,txn_timestamp",
        feature_set_version="v1",
        description="Share of returned transactions in rolling 180-day window ending at as_of.",
        transform_summary="SUM(is_returned) / COUNT(*) in (as_of - 180d, as_of]. Defaults to 0.0 for zero transactions.",
        business_rationale="Rising return rates reflect customer dissatisfaction or unmet expectations preceding churn.",
        parameters={"window_days": 180},
    ),
    FeatureSpec(
        name="txn_count_last_Nd",
        dtype="int64",
        nullable=False,
        source="data/transactions.db:transactions.txn_timestamp",
        feature_set_version="v2",  # Default latest version
        description="Count of transactions in rolling N-day window ending at as_of.",
        transform_summary="Count of transactions with txn_timestamp in (as_of - window_days, as_of]. Reindex over all customers, filling missing with 0.",
        business_rationale="Frequency in a recent window measures current buying velocity.",
        parameters={"window_days": 90},
    ),
    FeatureSpec(
        name="tenure_days",
        dtype="float64",
        nullable=False,
        source="data/customers.csv:customers.signup_date",
        feature_set_version="v1",
        description="Customer account age in days as of the as-of date.",
        transform_summary="(as_of - signup_date).days computed directly from customers profile table.",
        business_rationale="Newer customers have unproven habits and structurally higher churn hazard.",
        parameters={},
    ),
]
