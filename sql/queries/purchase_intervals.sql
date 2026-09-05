-- Per-customer gaps (in days) between consecutive purchase invoices.
-- Feeds the Phase 4 decision on where to set the churn inactivity
-- threshold, from the actual distribution of these gaps (e.g. a high
-- percentile of them) rather than a number picked in advance.
--
-- Only non-cancellation invoices count as "purchases" -- a return
-- doesn't reset a customer's purchase clock.

with customer_purchases as (
    select distinct
        i.customer_id,
        i.invoice_no,
        i.invoice_date
    from invoices i
    where i.customer_id is not null
      and not i.is_cancellation
),
ordered_purchases as (
    select
        customer_id,
        invoice_no,
        invoice_date,
        lag(invoice_date) over (partition by customer_id order by invoice_date) as prev_invoice_date
    from customer_purchases
)
select
    customer_id,
    invoice_no,
    invoice_date,
    (invoice_date::date - prev_invoice_date::date) as days_since_prev_purchase
from ordered_purchases
where prev_invoice_date is not null
order by customer_id, invoice_date;
