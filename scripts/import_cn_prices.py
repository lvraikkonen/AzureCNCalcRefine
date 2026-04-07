#!/usr/bin/env python3
"""Import ACN retail prices CSV into PostgreSQL retail_prices table.

Usage:
    uv run python scripts/import_cn_prices.py [--csv PATH] [--batch-size N]

Default CSV path: sample-data/AzureRetailPrices.csv
Requires DATABASE_URL environment variable.

Strategy: TRUNCATE + bulk INSERT (full refresh, MVP approach).
"""

import argparse
import csv
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()


# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.retail_price import CSV_TO_DB_COLUMNS

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "sample-data" / "AzureRetailPrices.csv"
BATCH_SIZE = 5000

# Columns that should be parsed as float
FLOAT_COLUMNS = {"tier_minimum_units", "retail_price", "unit_price"}
# Columns that should be parsed as boolean
BOOL_COLUMNS = {"is_primary_meter_region"}


def parse_row(csv_row: dict) -> dict:
    """Convert a CSV row (camelCase keys) to DB row (snake_case keys) with type coercion."""
    db_row = {}
    for csv_col, db_col in CSV_TO_DB_COLUMNS.items():
        raw = csv_row.get(csv_col, "").strip()

        if db_col in FLOAT_COLUMNS:
            db_row[db_col] = float(raw) if raw else 0.0
        elif db_col in BOOL_COLUMNS:
            db_row[db_col] = raw.lower() == "true" if raw else None
        else:
            db_row[db_col] = raw if raw else None

    return db_row


def import_csv(csv_path: Path, database_url: str, batch_size: int = BATCH_SIZE) -> int:
    """Import CSV into retail_prices table. Returns row count."""
    engine = create_engine(database_url)

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = [parse_row(row) for row in reader]

    total = len(rows)
    print(f"Parsed {total} rows from {csv_path.name}")

    db_columns = list(CSV_TO_DB_COLUMNS.values())
    placeholders = ", ".join(f":{col}" for col in db_columns)
    columns_str = ", ".join(db_columns)
    insert_sql = text(f"INSERT INTO retail_prices ({columns_str}) VALUES ({placeholders})")

    with engine.begin() as conn:
        # Full refresh: truncate then insert
        conn.execute(text("TRUNCATE TABLE retail_prices RESTART IDENTITY"))
        print("Truncated retail_prices table")

        # Batch insert
        imported = 0
        for i in range(0, total, batch_size):
            batch = rows[i : i + batch_size]
            conn.execute(insert_sql, batch)
            imported += len(batch)
            print(f"  Inserted {imported}/{total} rows...")

    print(f"Import complete: {total} rows")

    # Verify
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM retail_prices")).scalar()
        print(f"Verification: {count} rows in retail_prices table")

        # Show service_name distribution (top 10)
        result = conn.execute(text(
            "SELECT service_name, COUNT(*) as cnt "
            "FROM retail_prices GROUP BY service_name "
            "ORDER BY cnt DESC LIMIT 10"
        ))
        print("\nTop 10 services by row count:")
        for row in result:
            print(f"  {row[0]}: {row[1]}")

    return total


def main():
    parser = argparse.ArgumentParser(description="Import ACN CSV into retail_prices")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Path to CSV file")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Batch insert size")
    args = parser.parse_args()

    from app.database import build_database_url

    try:
        database_url = build_database_url(driver="")  # sync psycopg2
    except RuntimeError as e:
        print(f"ERROR: {e}")
        print("  Check .env file for DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD")
        sys.exit(1)

    if not args.csv.exists():
        print(f"ERROR: CSV file not found: {args.csv}")
        sys.exit(1)

    import_csv(args.csv, database_url, args.batch_size)


if __name__ == "__main__":
    main()
