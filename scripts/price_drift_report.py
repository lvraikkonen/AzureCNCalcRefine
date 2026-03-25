"""
Generate a price drift report comparing ACN legacy prices with CN CSV data.

Usage: uv run python scripts/price_drift_report.py

Compares data/acn_price_validation.json (legacy CNY prices from calculatordatamodel.js)
against the retail_prices PostgreSQL table (imported from CN CSV).

Requires a running database with imported data. If the database is not available,
prints a summary of the legacy price data instead.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRICES_PATH = ROOT / "data" / "acn_price_validation.json"


def report_legacy_summary():
    """Print a summary of the legacy price data."""
    data = json.loads(PRICES_PATH.read_text("utf-8"))

    total_products = len(data)
    total_prices = sum(len(v["prices"]) for v in data.values())

    # Count by price type
    by_type = {}
    for slug, info in data.items():
        for p in info["prices"]:
            pt = p.get("type", "unknown")
            by_type[pt] = by_type.get(pt, 0) + 1

    print("=" * 60)
    print("ACN Legacy Price Data Summary")
    print("=" * 60)
    print(f"Products:     {total_products}")
    print(f"Price entries: {total_prices}")
    print(f"\nBy pricing type:")
    for pt, count in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {pt:10s}: {count:5d}")

    # Products with most price entries
    by_count = sorted(data.items(), key=lambda x: -len(x[1]["prices"]))
    print(f"\nTop 10 products by price entry count:")
    for slug, info in by_count[:10]:
        print(f"  {slug:45s}: {len(info['prices']):4d} ({info['display_name'][:30]})")

    # Sample some prices
    print(f"\nSample prices (first 5 products):")
    for slug, info in list(data.items())[:5]:
        print(f"\n  {slug} ({info['display_name'][:40]}):")
        for p in info["prices"][:3]:
            desc = f"{p.get('type_name','')}/{p.get('size_name','')}"
            print(f"    {desc:30s} {p.get('type',''):8s} CNY {p.get('price',0):.4f}/{p.get('period','')}")
        if len(info["prices"]) > 3:
            print(f"    ... and {len(info['prices']) - 3} more")


def report_with_db():
    """Compare legacy prices with database prices."""
    try:
        from sqlalchemy import create_engine, text
        from app.core.config import settings
        engine = create_engine(str(settings.DATABASE_URL))
    except Exception as e:
        print(f"Database not available: {e}")
        print("Falling back to legacy-only summary.\n")
        report_legacy_summary()
        return

    data = json.loads(PRICES_PATH.read_text("utf-8"))

    # Query all service names from DB
    with engine.connect() as conn:
        result = conn.execute(text("SELECT DISTINCT service_name FROM retail_prices"))
        db_services = {row[0] for row in result}

    print("=" * 60)
    print("Price Drift Report: ACN Legacy vs CN CSV")
    print("=" * 60)
    print(f"Legacy products: {len(data)}")
    print(f"DB services:     {len(db_services)}")

    # Simple coverage check
    matched = 0
    not_in_db = []
    for slug, info in data.items():
        name = info.get("display_name", slug)
        # Check if any DB service name contains part of the legacy name
        found = any(name.lower() in svc.lower() or svc.lower() in name.lower()
                     for svc in db_services)
        if found:
            matched += 1
        else:
            not_in_db.append((slug, name))

    print(f"\nCoverage: {matched}/{len(data)} legacy products found in DB")
    if not_in_db:
        print(f"\nNot found in DB ({len(not_in_db)}):")
        for slug, name in not_in_db[:20]:
            print(f"  {slug}: {name}")
        if len(not_in_db) > 20:
            print(f"  ... and {len(not_in_db) - 20} more")


def main():
    if not PRICES_PATH.exists():
        print(f"Error: {PRICES_PATH} not found. Run extract_acn_metadata.py first.")
        sys.exit(1)

    if "--db" in sys.argv:
        report_with_db()
    else:
        report_legacy_summary()


if __name__ == "__main__":
    main()
