# Findings

One dataset (UCI Online Retail II, ~1M invoice lines, Dec 2009–Nov 2011
after trimming the incomplete final month), three connected analyses.
Full detail and reproduction steps are in the phase scripts; this is
the "so what."

## Segmentation: four real segments, not five arbitrary buckets

RFM features (recency, frequency, monetary — netting cancellations)
were clustered with k-means, choosing k by silhouette score rather than
picking a round number. **k=4 scored 0.41**, clearly beating the naive
"just split customers into monetary quintiles" baseline computed on the
same features (**0.08**) — the validated split captures real structure
a spreadsheet-style quintile cut does not.

| Segment | Customers | Avg. recency | Avg. frequency | Avg. monetary |
|---|---|---|---|---|
| Champions | 1,656 | 55 days | 16.1 orders | £8,256 |
| New / Occasional | 2,358 | 92 days | 2.9 orders | £861 |
| At Risk / Churned | 1,821 | 474 days | 1.9 orders | £572 |
| Net Negative / Returners | 46 | 379 days | 1.8 orders | **-£719** |

The last group is small but real: 46 customers whose returns net out
above their purchases — worth a manual look (fraud? damaged-goods
disputes?) rather than folding into a generic low-value bucket.

## Churn: risk clearly differs by segment, and one result cuts against intuition

Churn definition wasn't picked in advance: the inactivity threshold
(**135 days**) is the 90th percentile of actual gaps between a
customer's purchases — longer than 90% of normal reorder cycles counts
as churned. Under that definition, 45.2% of customers have churned as
of the data's end.

Kaplan-Meier curves per segment, tested with a log-rank test
(p ≈ 0), confirm churn risk is *not* uniform across segments —
Champions and New/Occasional customers are still mostly active past a
year, while At Risk/Churned and Net Negative/Returners drop off sharply
within months (see `reports/km_curves_by_segment.png`).

A Cox proportional hazards model quantifies it. Two results are
unsurprising: purchase frequency is strongly protective (each doubling
of order count cuts churn hazard by roughly 92%), and higher average
order value is mildly protective too.

**The non-obvious one:** holding individual frequency and order value
constant, the *New/Occasional* segment has a **lower** hazard ratio
(0.56×) than *Champions* — the segment with by far the highest spend
and frequency. Read naively, that says occasional shoppers outlast your
best customers, which would be a strange result. The more likely
explanation: New/Occasional customers are, on average, more recently
acquired, so they simply haven't had the calendar time to lapse yet —
their "survival" partly reflects youth, not loyalty. This is a caveat
worth building into any retention model built on this data, not a
headline to repeat uncritically.

At Risk/Churned customers carry **7.1×** the hazard of Champions, and
the Net Negative/Returners group **3.8×** — both intuitive, and useful
for prioritizing win-back campaigns.

## Forecast: monthly, honest about its limits

Weekly and monthly aggregation were both tested for which leaves a
cleaner signal after decomposition; the difference was marginal
(residual noise fraction ~0.001 vs ~0.000), so monthly was kept as both
the (very slightly) cleaner signal and the more natural reporting
cadence.

A SARIMAX model backtested on the last 3 real months (Sep–Nov 2011)
beat a seasonal-naive baseline (last year's same month) by a wide
margin — **MAE £45.8k vs. £76.9k**. But the error isn't uniform:
September was off by 9.3%, while October and November were within 2%.
That's reported as-is rather than only showing the best month.

The honest caveat: this dataset covers barely two full years, so the
model's annual seasonal term is fit from just over one full cycle of
training data (statsmodels flags this directly — "too few observations
to estimate starting parameters for seasonal ARMA"). Treat the forecast
as directionally useful for near-term planning, not as a precise
year-ahead seasonal model — more history would meaningfully tighten it.

## Putting it together

At Risk/Churned is nearly a third of the customer base (1,821 of
5,881) and has a 7× churn hazard relative to Champions — that's the
single highest-leverage retention target, not a diffuse "reduce churn"
goal. Champions drive a disproportionate share of monetary value and
show the least churn risk, so the forecast's near-term accuracy is
implicitly a bet on that segment's continued frequency — the same
`log_frequency` term that dominates the Cox model. The three analyses
aren't independent exercises; segment membership is the throughline
connecting who's valuable, who's leaving, and what that means for
near-term revenue.
