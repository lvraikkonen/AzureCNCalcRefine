"""In-memory cache for the product catalog.

The catalog is loaded from DB at startup (if DATABASE_URL is set) and falls
back to the JSON file in app/config/product_catalog.json.

The cache is a dict in the same shape as product_catalog.json:
  {"families": [{"key": ..., "label": ..., "order": ..., "services": [...]}]}
"""

import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

_catalog: dict | None = None
_CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "product_catalog.json"


def get_cached_catalog() -> dict | None:
    return _catalog


def set_cached_catalog(catalog: dict) -> None:
    global _catalog
    _catalog = catalog


def invalidate_catalog_cache() -> None:
    global _catalog
    _catalog = None


def load_catalog_from_json() -> dict:
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


async def load_catalog_to_cache(session: AsyncSession) -> None:
    """Load product catalog from DB into in-memory cache."""
    from app.services.config_repo import get_catalog

    families = await get_catalog(session)
    if not families:
        return  # DB empty — leave cache empty so JSON fallback is used

    catalog = {
        "families": [
            {
                "key": f.key,
                "label": f.label,
                "order": f.order,
                "services": [
                    {
                        "service_name": s.service_name,
                        "description": s.description,
                        "icon": s.icon,
                        "popular": s.popular,
                        "display_name_cn": s.display_name_cn,
                        "region_constraints": s.region_constraints,
                    }
                    for s in f.services
                ],
            }
            for f in families
        ]
    }
    set_cached_catalog(catalog)
