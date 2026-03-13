"""Products API — serves the product catalog for the navigation area."""

import json
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/products", tags=["products"])

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "product_catalog.json"
_catalog: dict | None = None


def _load_catalog() -> dict:
    global _catalog
    if _catalog is None:
        _catalog = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    return _catalog


@router.get("/catalog")
async def get_catalog():
    """Return the full product catalog (families + services)."""
    return _load_catalog()


@router.get("/search")
async def search_products(q: str = Query(..., min_length=1)):
    """Search services by name or description (case-insensitive substring match)."""
    catalog = _load_catalog()
    query = q.lower()
    results = []
    for family in catalog["families"]:
        for svc in family["services"]:
            if (query in svc["service_name"].lower()
                    or query in svc["description"].lower()):
                results.append({
                    **svc,
                    "family_key": family["key"],
                    "family_label": family["label"],
                })
    return {"query": q, "results": results}
