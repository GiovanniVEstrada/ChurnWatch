# ChurnWatch

Customer analytics engine built on one real transactional dataset:
statistically-validated customer segmentation, survival-based churn
prediction per segment, and backtested sales forecasting — three
connected analyses on top of a normalized SQL data layer, not three
disconnected tutorial exercises.

## Dataset

[UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii)
(CC BY 4.0) — invoice-level transactions from a UK-based online gift
retailer, Dec 2009–Dec 2011 (~1M rows). No pre-computed RFM scores or
churn labels ship with it; segmentation and churn definitions are
derived from the raw invoices, not given columns.

Known cleanup handled at load time (see
[scripts/ingest/load_to_postgres.py](scripts/ingest/load_to_postgres.py)):
invoices prefixed `C` are cancellations, flagged rather than dropped;
rows with no `Customer ID` are excluded from customer-level tables but
kept for aggregate sales forecasting.

## Stack

- **Data layer:** PostgreSQL (via Docker), normalized schema loaded from
  the raw CSV through documented SQL/Python — no manual spreadsheet
  editing anywhere in the pipeline.
- **Analysis:** Python — pandas, scikit-learn (clustering), lifelines
  (survival analysis), statsmodels (forecasting).
- **Visualization:** Power BI / Tableau, one dashboard tying all three
  findings together.

## Getting started

```bash
cp .env.example .env               # defaults are fine for local dev

make venv                          # create .venv, install requirements
source .venv/bin/activate

make up                            # start Postgres in Docker, apply schema

make download                      # fetch raw dataset -> data/raw/
make load                          # clean + load into Postgres
```

Verify the load:

```bash
make psql
churnwatch=# select count(*) from invoice_items;
```

## Project structure

```
sql/                  DDL and documented query layer (Phase 2)
scripts/ingest/        download + load raw data into Postgres (Phase 1)
scripts/segmentation/  RFM + k-means, silhouette/gap validation (Phase 3)
scripts/churn/         Kaplan-Meier + Cox proportional hazards (Phase 4)
scripts/forecasting/   decomposition + backtested forecast (Phase 5)
notebooks/             exploratory work supporting each phase
dashboard/             Power BI / Tableau file (Phase 6)
docs/writeup.md         plain-language findings (Phase 6)
```

## Roadmap

- [x] Phase 1 — Data ingestion & cleaning
- [x] Phase 2 — SQL exploration layer (RFM, per-period sales queries)
- [ ] Phase 3 — Segmentation (RFM → k-means → silhouette/gap statistic)
- [ ] Phase 4 — Churn analysis (Kaplan-Meier + Cox PH per segment)
- [ ] Phase 5 — Forecasting (decomposition → backtest → honest error)
- [ ] Phase 6 — Dashboard & write-up

Open questions to resolve during the relevant phase, not before: churn
inactivity threshold (Phase 4, from the actual purchase-interval
distribution) and forecast granularity (Phase 5, from how noisy the
aggregated series looks after decomposition).

## Out of scope

Deep learning / neural forecasting, real-time or streaming pipelines,
and generalizing this into a reusable framework for arbitrary datasets.
This is tuned for this dataset, as a finished analysis, not a platform.
