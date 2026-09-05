-- Monthly net sales -- the input to Phase 5 time-series decomposition
-- and forecasting.
--
-- Deliberately not joined to customers: this is aggregate revenue, so
-- guest checkouts with no Customer ID still count. Cancellations net
-- naturally since their line_total is already negative (see rfm.sql
-- for why that's true whether or not an invoice is 'C'-prefixed).
--
-- Note: the data ends 2011-12-09, so the last row (period = 2011-12-01)
-- covers only 9 days, not a full month. scripts/forecasting/sales_forecast.py
-- drops it before decomposition/backtesting for exactly this reason --
-- any other consumer of this query (e.g. the dashboard) should too.

select
    date_trunc('month', i.invoice_date)::date as period,
    sum(ii.line_total)             as net_sales,
    count(distinct i.invoice_no)   as invoice_count
from invoices i
join invoice_items ii on ii.invoice_no = i.invoice_no
group by 1
order by 1;
