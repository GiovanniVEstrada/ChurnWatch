# Dashboard

`index.html` is a self-contained, interactive dashboard tying all three
findings into one view: segment breakdown, churn risk by segment
(Kaplan-Meier curves + Cox hazard ratios), and the backtested sales
forecast.

It is built as an HTML page rather than a Power BI `.pbix` / Tableau
`.twbx` file — the analysis pipeline runs on Linux, where neither
desktop tool is available, and an HTML page is viewable by anyone
without a licensed client.

## Regenerating it

The page embeds its data rather than fetching it, so the numbers can't
drift from the pipeline silently. To refresh after re-running any
analysis phase:

```bash
python3 -m scripts.dashboard.export_dashboard_data   # -> reports/dashboard_data.json
```

then splice that JSON into the `<script id="dashboard-data">` block in
`index.html`. Every figure on the page — KPIs, segment table, survival
curves, hazard ratios, forecast backtest — is read from that block, so
nothing is hand-typed.
