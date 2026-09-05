"""Download UCI Online Retail II and cache it as a single raw CSV.

Source: https://archive.ics.uci.edu/dataset/502/online+retail+ii (CC BY 4.0)

The dataset isn't available through the ucimlrepo API (id=502 exists but
isn't import-enabled), so we pull the static zip UCI serves directly. It
contains one .xlsx workbook with two sheets -- "Year 2009-2010" and
"Year 2010-2011" -- which we concatenate into one raw CSV that later
steps treat as the immutable source of truth.
"""

import io
import zipfile
from pathlib import Path
from urllib.request import urlopen

import pandas as pd

DATASET_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
RAW_PATH = Path(__file__).resolve().parents[2] / "data" / "raw" / "online_retail_ii.csv"


def main() -> None:
    print(f"Downloading {DATASET_URL}")
    with urlopen(DATASET_URL) as resp:
        zip_bytes = resp.read()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        xlsx_name = next(n for n in zf.namelist() if n.endswith(".xlsx"))
        with zf.open(xlsx_name) as f:
            xlsx_bytes = io.BytesIO(f.read())

    sheets = pd.read_excel(xlsx_bytes, sheet_name=None, engine="openpyxl")
    df = pd.concat(sheets.values(), ignore_index=True)

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RAW_PATH, index=False)
    print(f"Wrote {len(df):,} rows from {len(sheets)} sheet(s) to {RAW_PATH}")


if __name__ == "__main__":
    main()
