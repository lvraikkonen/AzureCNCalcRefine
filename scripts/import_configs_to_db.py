"""Import existing JSON config files and product_catalog.json into the database.

Usage:
    DATABASE_URL=postgresql+asyncpg://user:password@host/db uv run python scripts/import_configs_to_db.py

Options:
    --dry-run    Print what would be imported without writing to DB
    --overwrite  Update existing records instead of skipping them

The script imports:
  1. All service_config JSON files from app/config/service_configs/*.json
  2. The product catalog from app/config/product_catalog.json
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_session_factory
from app.models.config import ProductFamily, ProductService, ServiceConfig, ServiceConfigHistory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

CONFIG_DIR = Path(__file__).resolve().parent.parent / "app" / "config" / "service_configs"
CATALOG_PATH = Path(__file__).resolve().parent.parent / "app" / "config" / "product_catalog.json"


def slug_from_service_name(service_name: str) -> str:
    return service_name.lower().replace(" ", "_")


async def import_service_config(
    session: AsyncSession,
    service_name: str,
    slug: str,
    config: dict,
    overwrite: bool,
    dry_run: bool,
) -> str:
    """Import one service config. Returns 'created', 'updated', or 'skipped'."""
    result = await session.execute(
        select(ServiceConfig).where(ServiceConfig.service_name == service_name)
    )
    existing = result.scalar_one_or_none()

    if existing:
        if not overwrite:
            return "skipped"
        if dry_run:
            return "updated (dry-run)"
        existing.config = config
        existing.slug = slug
        existing.status = "published"
        existing.version += 1
        session.add(
            ServiceConfigHistory(
                service_config_id=existing.id,
                version=existing.version - 1,
                config=existing.config,
                status=existing.status,
                changed_by="import_script",
                change_summary="Re-imported from JSON file",
            )
        )
        return "updated"

    if dry_run:
        return "created (dry-run)"

    obj = ServiceConfig(
        service_name=service_name,
        slug=slug,
        config=config,
        status="published",
        version=1,
        updated_by="import_script",
    )
    session.add(obj)
    await session.flush()
    session.add(
        ServiceConfigHistory(
            service_config_id=obj.id,
            version=1,
            config=config,
            status="published",
            changed_by="import_script",
            change_summary="Imported from JSON file",
        )
    )
    return "created"


async def import_catalog(
    session: AsyncSession,
    catalog: dict,
    overwrite: bool,
    dry_run: bool,
) -> dict[str, int]:
    counts = {"families_created": 0, "families_skipped": 0, "services_created": 0, "services_skipped": 0}

    for i, family_data in enumerate(catalog.get("families", [])):
        key = family_data["key"]
        label = family_data["label"]
        order = family_data.get("order", i)

        result = await session.execute(
            select(ProductFamily).where(ProductFamily.key == key)
        )
        family_obj = result.scalar_one_or_none()

        if family_obj:
            if overwrite and not dry_run:
                family_obj.label = label
                family_obj.order = order
            counts["families_skipped"] += 1
        else:
            if not dry_run:
                family_obj = ProductFamily(key=key, label=label, order=order)
                session.add(family_obj)
                await session.flush()
            counts["families_created"] += 1

        for j, svc_data in enumerate(family_data.get("services", [])):
            service_name = svc_data["service_name"]

            result = await session.execute(
                select(ProductService).where(ProductService.service_name == service_name)
            )
            svc_obj = result.scalar_one_or_none()

            if svc_obj:
                if overwrite and not dry_run:
                    svc_obj.description = svc_data.get("description", "")
                    svc_obj.icon = svc_data.get("icon")
                    svc_obj.popular = svc_data.get("popular", False)
                    svc_obj.order = j
                counts["services_skipped"] += 1
            else:
                if not dry_run and family_obj is not None:
                    svc_obj = ProductService(
                        family_id=family_obj.id,
                        service_name=service_name,
                        description=svc_data.get("description", ""),
                        icon=svc_data.get("icon"),
                        popular=svc_data.get("popular", False),
                        order=j,
                    )
                    session.add(svc_obj)
                counts["services_created"] += 1

    return counts


async def main(overwrite: bool, dry_run: bool) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.")
        sys.exit(1)

    print(f"{'[DRY RUN] ' if dry_run else ''}Connecting to database...")
    factory = get_session_factory()

    async with factory() as session:
        # --- Import service configs ---
        config_files = sorted(CONFIG_DIR.glob("*.json"))
        print(f"\nFound {len(config_files)} service config file(s) in {CONFIG_DIR}")

        config_counts = {"created": 0, "updated": 0, "skipped": 0}
        for config_path in config_files:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            service_name = config.get("service_name", "")
            if not service_name:
                # Derive from filename
                service_name = config_path.stem.replace("_", " ").title()
            slug = config_path.stem

            action = await import_service_config(
                session, service_name, slug, config, overwrite, dry_run
            )
            verb = action.split(" ")[0]
            if verb in config_counts:
                config_counts[verb] += 1
            print(f"  [{action}] {service_name} ({slug}.json)")

        if not dry_run:
            await session.commit()

        print(f"\nService configs: {config_counts}")

        # --- Import product catalog ---
        print(f"\nImporting product catalog from {CATALOG_PATH}")
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        catalog_counts = await import_catalog(session, catalog, overwrite, dry_run)

        if not dry_run:
            await session.commit()

        print(f"Catalog: {catalog_counts}")
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Import complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import JSON configs into database")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing to DB")
    parser.add_argument("--overwrite", action="store_true", help="Update existing records")
    args = parser.parse_args()
    asyncio.run(main(overwrite=args.overwrite, dry_run=args.dry_run))
