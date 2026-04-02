"""Shared client for Azure Global Retail Prices API.

Async version of the logic in scripts/explore_global_api.py,
used by FastAPI route handlers.
"""

import httpx

GLOBAL_API_URL = "https://prices.azure.com/api/retail/prices"


def get_effective_term(item: dict) -> str:
    """Return effective term: reservationTerm for Reservation, else term."""
    return item.get("reservationTerm") or item.get("term") or ""


async def fetch_global_prices(filters: dict, max_pages: int = 10) -> list[dict]:
    """Query Azure Global Retail Prices API with OData filters."""
    parts = [f"{k} eq '{v}'" for k, v in filters.items()]
    odata_filter = " and ".join(parts)

    items: list[dict] = []
    url = GLOBAL_API_URL
    params: dict = {"$filter": odata_filter}

    async with httpx.AsyncClient(timeout=30) as client:
        for _ in range(max_pages):
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get("Items", []))
            next_link = data.get("NextPageLink")
            if not next_link:
                break
            url = next_link
            params = {}

    return items


def filter_primary_non_devtest(items: list[dict]) -> list[dict]:
    """Standard filter: isPrimaryMeterRegion=True + exclude DevTestConsumption.

    Only safe for services whose meters have isPrimaryMeterRegion=True in the
    queried region (e.g. Virtual Machines in eastus).  For globally-priced
    services (Service Bus, Azure Firewall, Event Grid …) most or all rows in
    a concrete region are isPrimary=False — use filter_non_devtest() instead.

    Background: each meterId has exactly ONE primary region.  Old/global
    meters set primary to "Global" and broadcast copies (isPrimary=False) to
    every concrete region at the same price.  Newer region-specific meters
    have their own meterId with isPrimary=True only in that region.
    """
    return [
        i for i in items
        if i.get("isPrimaryMeterRegion", True)
        and i.get("type") != "DevTestConsumption"
    ]


def filter_non_devtest(items: list[dict]) -> list[dict]:
    """Exclude DevTestConsumption only (no isPrimaryMeterRegion filter).

    Used by cascade/meters for services where isPrimaryMeterRegion=True would
    incorrectly drop all data.  Examples:
    - Service Bus eastus:  9/10 rows isPrimary=False (old global meterId)
    - Azure Firewall eastus: ALL rows isPrimary=False
    - Traffic Manager: global service, armRegionName is zone-based

    Prices in isPrimary=False rows are identical to their primary copies, so
    keeping them is safe — but callers must deduplicate by
    (meterName, unitOfMeasure, tierMinimumUnits) when needed.
    """
    return [i for i in items if i.get("type") != "DevTestConsumption"]


def build_api_filters(
    service_name: str,
    region: str | None = None,
    product: str | None = None,
    sku: str | None = None,
) -> dict[str, str]:
    """Build OData filter dict from common parameters."""
    filters: dict[str, str] = {"serviceName": service_name}
    if region:
        filters["armRegionName"] = region
    if product:
        filters["productName"] = product
    if sku:
        filters["skuName"] = sku
    return filters


def calculate_tiered_cost(tiers: list[dict], usage: float) -> float:
    """Calculate cost for tiered pricing.

    Each tier covers usage from its tierMinimumUnits to the next tier's threshold.
    """
    sorted_tiers = sorted(tiers, key=lambda t: float(t.get("tierMinimumUnits", 0)))
    total = 0.0

    for i, tier in enumerate(sorted_tiers):
        tier_start = float(tier.get("tierMinimumUnits", 0))
        tier_price = float(tier.get("unitPrice", 0))

        if usage <= tier_start:
            break

        if i + 1 < len(sorted_tiers):
            tier_end = float(sorted_tiers[i + 1].get("tierMinimumUnits", 0))
        else:
            tier_end = float("inf")

        tier_usage = min(usage, tier_end) - tier_start
        total += tier_usage * tier_price

    return total
