# Query layer

Documented aggregation queries live here once Phase 2 (SQL exploration
layer) starts — each one feeds a specific downstream analysis:

- `rfm.sql` — per-customer recency / frequency / monetary, the feature
  input to segmentation (Phase 3).
- `sales_by_period.sql` — per-period (weekly/monthly) net sales, the
  input to time-series decomposition and forecasting (Phase 5).
- `purchase_intervals.sql` — per-customer gaps between consecutive
  invoices, used to set the churn inactivity threshold empirically
  (Phase 4) instead of guessing a number up front.

Each query file should note here how it treats cancellations (netted
vs. excluded) since that decision affects every number downstream.
