"""Shared Postgres connection helper, configured via .env."""

import os

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine

load_dotenv()


def get_engine() -> Engine:
    user = os.environ.get("POSTGRES_USER", "churnwatch")
    password = os.environ.get("POSTGRES_PASSWORD", "churnwatch")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "churnwatch")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)
