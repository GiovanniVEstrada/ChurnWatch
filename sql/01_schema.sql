-- ChurnWatch: normalized schema for UCI Online Retail II
--
-- Source data is one flat invoice-line table. We normalize it into
-- customers / products / invoices / invoice_items so the SQL layer
-- demonstrates real joins instead of querying one denormalized blob.
--
-- Notes on source data quirks (handled at load time, not here):
--   - invoice_no prefixed 'C' = cancellation, netted against the original
--     sale in analysis queries rather than dropped.
--   - customer_id is NULL for a portion of rows (guest/unidentified
--     checkouts) -- those rows are excluded from customer-level tables
--     but kept in invoice_items for aggregate sales forecasting.

DROP TABLE IF EXISTS invoice_items CASCADE;
DROP TABLE IF EXISTS invoices CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE customers (
    customer_id     INTEGER PRIMARY KEY,
    country         TEXT NOT NULL
);

CREATE TABLE products (
    stock_code      TEXT PRIMARY KEY,
    description     TEXT
);

CREATE TABLE invoices (
    invoice_no      TEXT PRIMARY KEY,
    customer_id     INTEGER REFERENCES customers(customer_id),
    invoice_date    TIMESTAMP NOT NULL,
    is_cancellation BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE invoice_items (
    invoice_item_id BIGSERIAL PRIMARY KEY,
    invoice_no      TEXT NOT NULL REFERENCES invoices(invoice_no),
    stock_code      TEXT NOT NULL REFERENCES products(stock_code),
    quantity        INTEGER NOT NULL,
    unit_price      NUMERIC(12, 4) NOT NULL,
    line_total      NUMERIC(14, 4) GENERATED ALWAYS AS (quantity * unit_price) STORED
);

CREATE INDEX idx_invoices_customer_id  ON invoices(customer_id);
CREATE INDEX idx_invoices_date         ON invoices(invoice_date);
CREATE INDEX idx_invoice_items_invoice ON invoice_items(invoice_no);
CREATE INDEX idx_invoice_items_product ON invoice_items(stock_code);

COMMENT ON TABLE customers IS 'One row per distinct CustomerID present in the source data (NULL CustomerID rows are excluded here).';
COMMENT ON TABLE invoices IS 'One row per InvoiceNo. is_cancellation = TRUE when InvoiceNo was prefixed C in source.';
COMMENT ON TABLE invoice_items IS 'One row per invoice line. Included even when customer_id is unknown, to support aggregate (non-customer-level) sales forecasting.';
