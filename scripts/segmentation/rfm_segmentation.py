"""RFM customer segmentation: k-means validated by silhouette score.

Reads the RFM features produced by sql/queries/rfm.sql, transforms them
to tame skew (frequency and monetary are heavy-tailed; monetary can be
negative for customers who net more returns than purchases), scales
them, and fits k-means for a range of k. The k that maximizes silhouette
score wins -- not a fixed "5 segments" default. That silhouette score is
also computed for the naive NTILE(5) monetary quintile the SQL query
carries as a baseline, so the report shows the validated clustering is
actually better than an arbitrary split, not just different from it.

Output: a `customer_segments` table in Postgres (customer_id, RFM
features, cluster id, and a rule-based descriptive label), replacing
any previous run -- this table is fully derived and reproducible from
the raw data, so it's safe to regenerate rather than migrate.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from scripts.utils.db import get_engine

RFM_QUERY_PATH = Path(__file__).resolve().parents[2] / "sql" / "queries" / "rfm.sql"
K_RANGE = range(2, 9)
RANDOM_STATE = 42


def load_rfm(engine) -> pd.DataFrame:
    query = RFM_QUERY_PATH.read_text()
    return pd.read_sql(query, engine)


def transform_features(rfm: pd.DataFrame) -> np.ndarray:
    recency = rfm["recency_days"].to_numpy(dtype=float)
    freq_log = np.log1p(rfm["frequency"].to_numpy(dtype=float))
    monetary = rfm["monetary"].to_numpy(dtype=float)
    monetary_signed_log = np.sign(monetary) * np.log1p(np.abs(monetary))

    features = np.column_stack([recency, freq_log, monetary_signed_log])
    return StandardScaler().fit_transform(features)


def choose_k(X: np.ndarray) -> tuple[int, dict[int, float]]:
    scores = {}
    for k in K_RANGE:
        labels = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10).fit_predict(X)
        scores[k] = silhouette_score(X, labels)
    best_k = max(scores, key=scores.get)
    return best_k, scores


def label_segments(rfm: pd.DataFrame) -> pd.Series:
    """Rule-based label from each cluster's centroid, relative to the overall median."""
    med_recency = rfm["recency_days"].median()
    med_frequency = rfm["frequency"].median()
    med_monetary = rfm["monetary"].median()

    centroids = rfm.groupby("segment")[["recency_days", "frequency", "monetary"]].mean()

    def label_row(row) -> str:
        if row["monetary"] < 0:
            return "Net Negative / Returners"
        recent = row["recency_days"] <= med_recency
        frequent = row["frequency"] >= med_frequency
        high_value = row["monetary"] >= med_monetary
        if recent and frequent and high_value:
            return "Champions"
        if not recent and not frequent:
            return "At Risk / Churned"
        if recent and not frequent:
            return "New / Occasional"
        if high_value:
            return "Loyal High-Value"
        return "Loyal Low-Value"

    centroid_labels = centroids.apply(label_row, axis=1)
    return rfm["segment"].map(centroid_labels)


def main() -> None:
    engine = get_engine()
    rfm = load_rfm(engine)
    print(f"Loaded RFM features for {len(rfm):,} customers")

    X = transform_features(rfm)

    best_k, scores = choose_k(X)
    print("\nSilhouette score by k:")
    for k, s in scores.items():
        marker = "  <- chosen" if k == best_k else ""
        print(f"  k={k}: {s:.4f}{marker}")

    naive_labels = rfm["naive_monetary_quintile"].to_numpy()
    naive_score = silhouette_score(X, naive_labels)
    print(f"\nNaive NTILE(5) monetary-quintile baseline silhouette: {naive_score:.4f}")
    print(f"Validated k={best_k} k-means silhouette:                {scores[best_k]:.4f}")
    if scores[best_k] > naive_score:
        print("-> k-means beats the naive quintile split.")
    else:
        print("-> WARNING: k-means does not beat the naive quintile split; investigate features/k range.")

    final_model = KMeans(n_clusters=best_k, random_state=RANDOM_STATE, n_init=10)
    rfm["segment"] = final_model.fit_predict(X)
    rfm["segment_label"] = label_segments(rfm)

    print("\nSegment summary:")
    summary = rfm.groupby(["segment", "segment_label"]).agg(
        customers=("customer_id", "count"),
        avg_recency_days=("recency_days", "mean"),
        avg_frequency=("frequency", "mean"),
        avg_monetary=("monetary", "mean"),
    ).round(1)
    print(summary.to_string())

    with engine.begin() as conn:
        rfm.to_sql("customer_segments", conn, if_exists="replace", index=False)
    print(f"\nWrote {len(rfm):,} rows to customer_segments")


if __name__ == "__main__":
    main()
