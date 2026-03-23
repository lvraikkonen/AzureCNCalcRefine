"""Products API — serves the product catalog for the navigation area."""

from fastapi import APIRouter, Query

from app.services.catalog_cache import get_cached_catalog, load_catalog_from_json

router = APIRouter(prefix="/api/v1/products", tags=["products"])


def _load_catalog() -> dict:
    """Return the product catalog: DB cache first, JSON file fallback."""
    cached = get_cached_catalog()
    if cached is not None:
        return cached
    return load_catalog_from_json()


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
