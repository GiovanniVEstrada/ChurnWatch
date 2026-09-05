"""Load the raw Online Retail II CSV into the normalized Postgres schema.

Cleaning decisions made here (see README for rationale):
  - Rows missing Invoice or StockCode are dropped -- they can't anchor a
    line item to anything.
  - Rows missing Customer ID are kept in invoice_items (needed for
    aggregate sales forecasting) but the parent invoice's customer_id is
    NULL, so they're naturally excluded from customer-level tables/joins.
  - Invoices numbered with a 'C' prefix are flagged is_cancellation=TRUE,
    not dropped and not netted -- netting vs. separate modeling is an
    analysis-layer decision (Phase 3/4), not a data-loss decision here.
  - A customer's country is taken as their most frequent country across
    rows (a handful of customers have inconsistent country values).
  - A product's description is taken as the most common non-null
    description for that stock code (descriptions vary/are blank across
    rows for the same code).
"""

from pathlib import Path

import pandas as pd

from scripts.utils.db import get_engine

RAW_PATH = Path(__file__).resolve().parents[2] / "data" / "raw" / "online_retail_ii.csv"


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(RAW_PATH, dtype={"Customer ID": "Int64"}, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    df = df.dropna(subset=["Invoice", "StockCode"]).copy()
    df["Invoice"] = df["Invoice"].astype(str).str.strip()
    df["StockCode"] = df["StockCode"].astype(str).str.strip()
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    df["is_cancellation"] = df["Invoice"].str.startswith("C")
    print(f"Dropped {before - len(df):,} rows missing Invoice/StockCode ({before:,} -> {len(df):,})")
    return df


def build_customers(df: pd.DataFrame) -> pd.DataFrame:
    with_customer = df.dropna(subset=["Customer ID"])
    country_mode = (
        with_customer.groupby("Customer ID")["Country"]
        .agg(lambda s: s.mode().iat[0])
        .reset_index()
    )
    country_mode.columns = ["customer_id", "country"]
    country_mode["customer_id"] = country_mode["customer_id"].astype(int)
    return country_mode


def build_products(df: pd.DataFrame) -> pd.DataFrame:
    def pick_description(s: pd.Series) -> str | None:
        s = s.dropna()
        return s.mode().iat[0] if not s.empty else None

    products = (
        df.groupby("StockCode")["Description"]
        .agg(pick_description)
        .reset_index()
    )
    products.columns = ["stock_code", "description"]
    return products


def build_invoices(df: pd.DataFrame) -> pd.DataFrame:
    invoices = (
        df.groupby("Invoice")
        .agg(
            customer_id=("Customer ID", "first"),
            invoice_date=("InvoiceDate", "min"),
            is_cancellation=("is_cancellation", "first"),
        )
        .reset_index()
    )
    invoices.columns = ["invoice_no", "customer_id", "invoice_date", "is_cancellation"]
    invoices["customer_id"] = invoices["customer_id"].astype("Int64")
    return invoices


def build_invoice_items(df: pd.DataFrame) -> pd.DataFrame:
    items = df[["Invoice", "StockCode", "Quantity", "Price"]].copy()
    items.columns = ["invoice_no", "stock_code", "quantity", "unit_price"]
    return items


def main() -> None:
    raw = load_raw()
    df = clean(raw)

    customers = build_customers(df)
    products = build_products(df)
    invoices = build_invoices(df)
    invoice_items = build_invoice_items(df)

    engine = get_engine()
    with engine.begin() as conn:
        customers.to_sql("customers", conn, if_exists="append", index=False)
        products.to_sql("products", conn, if_exists="append", index=False)
        invoices.to_sql("invoices", conn, if_exists="append", index=False, chunksize=10_000)
        invoice_items.to_sql(
            "invoice_items", conn, if_exists="append", index=False, chunksize=10_000, method="multi"
        )

    print(f"Loaded: {len(customers):,} customers, {len(products):,} products, "
          f"{len(invoices):,} invoices, {len(invoice_items):,} invoice_items")
    print(f"Source raw row count: {len(raw):,} (post-clean: {len(df):,})")


if __name__ == "__main__":
    main()
