-- Per-customer Recency, Frequency, Monetary features -- the input to
-- Phase 3 segmentation (k-means, validated by silhouette/gap statistic).
--
-- Cancellations: monetary nets them against sales, since a return
-- already carries negative quantity/line_total in the source data
-- (whether posted against a 'C'-prefixed invoice or as a same-invoice
-- adjustment) and genuinely reduces what the customer is worth.
-- Frequency counts only non-cancellation invoices, since a return
-- isn't a new purchase occasion.
--
-- naive_monetary_quintile (NTILE(5)) is included only as the "arbitrary
-- quintile split" baseline the success criteria call out -- Phase 3's
-- k-means segmentation needs to demonstrably beat this, not just exist.

with snapshot as (
    select max(invoice_date) + interval '1 day' as snapshot_date
    from invoices
),
customer_invoice_revenue as (
    select
        i.customer_id,
        i.invoice_no,
        i.invoice_date,
        i.is_cancellation,
        sum(ii.line_total) as invoice_net_revenue
    from invoices i
    join invoice_items ii on ii.invoice_no = i.invoice_no
    where i.customer_id is not null
    group by i.customer_id, i.invoice_no, i.invoice_date, i.is_cancellation
),
customer_rfm as (
    select
        customer_id,
        max(invoice_date) filter (where not is_cancellation)         as last_purchase_date,
        count(distinct invoice_no) filter (where not is_cancellation) as frequency,
        sum(invoice_net_revenue)                                      as monetary
    from customer_invoice_revenue
    group by customer_id
)
select
    r.customer_id,
    (select snapshot_date from snapshot)::date - r.last_purchase_date::date as recency_days,
    r.frequency,
    round(r.monetary, 2) as monetary,
    ntile(5) over (order by r.monetary) as naive_monetary_quintile
from customer_rfm r
where r.frequency > 0  -- excludes customers whose only activity was a cancellation
order by r.customer_id;
