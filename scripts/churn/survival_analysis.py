"""Survival-based churn analysis: Kaplan-Meier per segment + Cox PH model.

Churn definition (duration/event), built for non-contractual retail
where there's no explicit cancellation event:
  - snapshot_date = max(invoice_date) + 1 day (consistent with rfm.sql).
  - churn_threshold_days is NOT fixed in advance -- it's the 90th
    percentile of the actual per-customer purchase-interval distribution
    from sql/queries/purchase_intervals.sql, i.e. "longer than 90% of
    normal gaps between purchases," rounded to the nearest day.
  - event = 1 (churned) if (snapshot_date - last_purchase_date) exceeds
    that threshold -- enough time has passed with no purchase that we
    call it churn. duration = (last_purchase_date - first_purchase_date),
    i.e. how long they stayed active before the purchase that turned out
    to be their last.
  - event = 0 (censored) otherwise -- not enough time has passed since
    their last purchase to conclude they've churned; they may still come
    back. duration = (snapshot_date - first_purchase_date), i.e. how
    long we've observed them so far.

Cox covariates deliberately exclude anything recency-derived (that would
be tautological with the event definition itself). Segment membership
comes from Phase 3's customer_segments table, directly connecting the
two analyses: does validated segmentation actually predict churn risk?
"""

from pathlib import Path

import numpy as np
import pandas as pd
from lifelines import CoxPHFitter, KaplanMeierFitter
from lifelines.statistics import multivariate_logrank_test

from scripts.utils.db import get_engine

PURCHASE_INTERVALS_QUERY_PATH = (
    Path(__file__).resolve().parents[2] / "sql" / "queries" / "purchase_intervals.sql"
)
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "reports"

CUSTOMER_LIFECYCLE_QUERY = """
select
    i.customer_id,
    min(i.invoice_date) as first_purchase_date,
    max(i.invoice_date) as last_purchase_date,
    count(distinct i.invoice_no) as frequency,
    sum(ii.line_total) as monetary,
    max(c.country) as country
from invoices i
join invoice_items ii on ii.invoice_no = i.invoice_no
join customers c on c.customer_id = i.customer_id
where i.customer_id is not null
  and not i.is_cancellation
group by i.customer_id
"""


def compute_churn_threshold(engine) -> int:
    query = PURCHASE_INTERVALS_QUERY_PATH.read_text()
    intervals = pd.read_sql(query, engine)
    p90 = intervals["days_since_prev_purchase"].quantile(0.90)
    return int(round(p90))


def build_survival_frame(engine, threshold_days: int) -> pd.DataFrame:
    df = pd.read_sql(CUSTOMER_LIFECYCLE_QUERY, engine)
    df["first_purchase_date"] = pd.to_datetime(df["first_purchase_date"])
    df["last_purchase_date"] = pd.to_datetime(df["last_purchase_date"])

    snapshot_date = pd.Timestamp(df["last_purchase_date"].max()) + pd.Timedelta(days=1)
    days_since_last = (snapshot_date - df["last_purchase_date"]).dt.days

    df["event"] = (days_since_last > threshold_days).astype(int)
    df["duration"] = np.where(
        df["event"] == 1,
        (df["last_purchase_date"] - df["first_purchase_date"]).dt.days,
        (snapshot_date - df["first_purchase_date"]).dt.days,
    )

    segments = pd.read_sql("select customer_id, segment_label from customer_segments", engine)
    df = df.merge(segments, on="customer_id", how="inner")  # drops the 61 no-real-purchase customers

    df["log_frequency"] = np.log1p(df["frequency"])
    avg_order_value = df["monetary"] / df["frequency"]
    df["avg_order_value_signed_log"] = np.sign(avg_order_value) * np.log1p(np.abs(avg_order_value))
    df["is_uk"] = (df["country"] == "United Kingdom").astype(int)

    return df


def run_kaplan_meier(df: pd.DataFrame) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 6))
    kmf = KaplanMeierFitter()
    median_survival = {}
    for label, group in df.groupby("segment_label"):
        kmf.fit(group["duration"], event_observed=group["event"], label=f"{label} (n={len(group)})")
        kmf.plot_survival_function(ax=ax)
        median_survival[label] = kmf.median_survival_time_

    ax.set_title("Kaplan-Meier survival curves by segment (survival = still active)")
    ax.set_xlabel("Days since first purchase")
    ax.set_ylabel("Probability of not yet churning")
    fig.tight_layout()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "km_curves_by_segment.png"
    fig.savefig(out_path, dpi=150)
    print(f"Saved Kaplan-Meier plot to {out_path}")

    print("\nMedian survival time (days) by segment:")
    for label, median in median_survival.items():
        print(f"  {label}: {median}")

    result = multivariate_logrank_test(df["duration"], df["segment_label"], df["event"])
    print(f"\nLog-rank test across segments: statistic={result.test_statistic:.2f}, p={result.p_value:.2e}")
    if result.p_value < 0.05:
        print("-> Churn risk differs significantly by segment.")
    else:
        print("-> WARNING: no significant difference in churn risk across segments.")


def run_cox_model(df: pd.DataFrame) -> None:
    reference_segment = "Champions"
    segment_dummies = pd.get_dummies(df["segment_label"], prefix="segment", drop_first=False)
    segment_dummies = segment_dummies.drop(columns=[f"segment_{reference_segment}"])

    cox_df = pd.concat(
        [df[["duration", "event", "log_frequency", "avg_order_value_signed_log", "is_uk"]], segment_dummies],
        axis=1,
    )
    cox_df.columns = [c.replace(" ", "_").replace("/", "") for c in cox_df.columns]

    cph = CoxPHFitter()
    cph.fit(cox_df, duration_col="duration", event_col="event")

    print(f"\nCox proportional hazards model (reference segment: {reference_segment})")
    print(cph.summary[["coef", "exp(coef)", "p"]].round(4).to_string())

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "cox_model_summary.csv"
    cph.summary.to_csv(out_path)
    print(f"\nSaved full Cox summary to {out_path}")


def main() -> None:
    engine = get_engine()

    threshold_days = compute_churn_threshold(engine)
    print(f"Churn inactivity threshold: {threshold_days} days (90th percentile of purchase intervals)")

    df = build_survival_frame(engine, threshold_days)
    print(f"Survival frame: {len(df):,} customers, {df['event'].sum():,} churn events "
          f"({df['event'].mean():.1%}), {len(df) - df['event'].sum():,} censored")

    run_kaplan_meier(df)
    run_cox_model(df)


if __name__ == "__main__":
    main()
