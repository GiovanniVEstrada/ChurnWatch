"""Consolidate Phase 3-5 outputs into one JSON file for the Phase 6 dashboard.

Re-derives the Kaplan-Meier survival curves (Phase 4 only saved a static
PNG) so the dashboard can render them interactively, and pulls segment
summaries, Cox hazard ratios, and the forecast backtest together into a
single reproducible artifact -- no manual copy-pasting of numbers into
the dashboard.
"""

import json
from pathlib import Path

import pandas as pd
from lifelines import KaplanMeierFitter

from sklearn.metrics import silhouette_score

from scripts.churn.survival_analysis import build_survival_frame, compute_churn_threshold
from scripts.forecasting.sales_forecast import backtest, choose_granularity, load_daily_sales
from scripts.segmentation.rfm_segmentation import choose_k, load_rfm, transform_features
from scripts.utils.db import get_engine

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "reports" / "dashboard_data.json"


def segment_summary(engine) -> list[dict]:
    df = pd.read_sql("select * from customer_segments", engine)
    summary = (
        df.groupby("segment_label")
        .agg(
            customers=("customer_id", "count"),
            avg_recency_days=("recency_days", "mean"),
            avg_frequency=("frequency", "mean"),
            avg_monetary=("monetary", "mean"),
        )
        .round(1)
        .reset_index()
        .sort_values("avg_monetary", ascending=False)
    )
    return summary.to_dict(orient="records")


def kaplan_meier_curves(engine) -> dict:
    threshold_days = compute_churn_threshold(engine)
    df = build_survival_frame(engine, threshold_days)

    curves = {}
    kmf = KaplanMeierFitter()
    for label, group in df.groupby("segment_label"):
        kmf.fit(group["duration"], event_observed=group["event"], label=label)
        sf = kmf.survival_function_.reset_index()
        sf.columns = ["day", "survival"]
        curves[label] = {
            "n": int(len(group)),
            "days": sf["day"].round(0).astype(int).tolist(),
            "survival": sf["survival"].round(4).tolist(),
        }
    return {"threshold_days": threshold_days, "curves": curves}


def cox_hazard_ratios() -> list[dict]:
    cox_path = Path(__file__).resolve().parents[2] / "reports" / "cox_model_summary.csv"
    df = pd.read_csv(cox_path, index_col=0)
    df = df.reset_index().rename(columns={"index": "covariate", "exp(coef)": "hazard_ratio"})
    return df[["covariate", "hazard_ratio", "p"]].round(4).to_dict(orient="records")


def forecast_series(engine) -> dict:
    daily = load_daily_sales(engine)
    grain, series, seasonal_period = choose_granularity(daily)
    test_size = 12 if grain == "weekly" else 3
    result = backtest(series, seasonal_period, test_size)

    history = series.iloc[:-test_size]
    return {
        "grain": grain,
        "history": {
            "period": [d.strftime("%Y-%m-%d") for d in history.index],
            "net_sales": history.round(0).tolist(),
        },
        "backtest": {
            "period": [d.strftime("%Y-%m-%d") for d in result["test"].index],
            "actual": result["test"].round(0).tolist(),
            "forecast": result["forecast"].round(0).tolist(),
            "naive": result["naive_forecast"].round(0).tolist(),
        },
        "model_mae": round(result["model_mae"], 0),
        "model_rmse": round(result["model_rmse"], 0),
        "naive_mae": round(result["naive_mae"], 0),
        "naive_rmse": round(result["naive_rmse"], 0),
    }


def top_line_kpis(engine, segments: list[dict], churn_threshold_days: int, churn_rate_pct: float, forecast: dict) -> dict:
    rfm = load_rfm(engine)
    X = transform_features(rfm)
    best_k, scores = choose_k(X)
    naive_score = silhouette_score(X, rfm["naive_monetary_quintile"].to_numpy())

    return {
        "total_customers": sum(s["customers"] for s in segments),
        "chosen_k": best_k,
        "silhouette_score": round(scores[best_k], 3),
        "naive_silhouette_score": round(naive_score, 3),
        "churn_threshold_days": churn_threshold_days,
        "churn_rate_pct": churn_rate_pct,
        "model_mae": forecast["model_mae"],
        "naive_mae": forecast["naive_mae"],
        "mae_improvement_pct": round(100 * (1 - forecast["model_mae"] / forecast["naive_mae"]), 1),
    }


def main() -> None:
    engine = get_engine()

    segments = segment_summary(engine)
    churn = kaplan_meier_curves(engine)
    forecast = forecast_series(engine)

    threshold_days = compute_churn_threshold(engine)
    survival_df = build_survival_frame(engine, threshold_days)
    churn_rate_pct = round(100 * survival_df["event"].mean(), 1)

    kpis = top_line_kpis(engine, segments, threshold_days, churn_rate_pct, forecast)

    data = {
        "kpis": kpis,
        "segments": segments,
        "churn": churn,
        "cox": cox_hazard_ratios(),
        "forecast": forecast,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(data, indent=2, default=lambda o: None if pd.isna(o) else o))
    print(f"Wrote dashboard data to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
