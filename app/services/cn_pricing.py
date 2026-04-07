"""CN pricing query service — queries local PostgreSQL retail_prices table.

Returns data in the same camelCase dict format as the Global API,
so upstream code (explore.py, pricing.js) doesn't need to know the data source.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session_factory
from app.models.retail_price import DB_TO_API_COLUMNS, RetailPrice


def _row_to_api_dict(row: RetailPrice) -> dict:
    """Convert a RetailPrice ORM row to a camelCase dict matching Global API format."""
    result = {}
    for db_col, api_col in DB_TO_API_COLUMNS.items():
        value = getattr(row, db_col, None)
        # Convert None to empty string for string fields (matching Global API behavior)
        if value is None and db_col not in ("is_primary_meter_region", "tier_minimum_units",
                                             "retail_price", "unit_price"):
            value = ""
        result[api_col] = value

    # Global API uses "reservationTerm" for Reservation type, "term" is always empty string.
    # CN CSV has the term value in the "term" column for all types.
    # Normalize: if type is Reservation or SavingsPlanConsumption, copy term → reservationTerm
    item_type = result.get("type", "")
    term_val = result.get("term", "")
    if item_type in ("Reservation", "SavingsPlanConsumption") and term_val:
        result["reservationTerm"] = term_val
    else:
        result["reservationTerm"] = ""

    return result


async def fetch_cn_prices(filters: dict[str, str]) -> list[dict]:
    """Query CN retail_prices from PostgreSQL with filters.

    Args:
        filters: camelCase field names → values, same format as Global API filters.
                 e.g. {"serviceName": "Redis Cache", "armRegionName": "chinaeast2"}

    Returns:
        List of dicts in camelCase format matching Global API response.
    """
    # Map camelCase filter keys to snake_case column names
    api_to_db = {v: k for k, v in DB_TO_API_COLUMNS.items()}

    stmt = select(RetailPrice)

    for api_field, value in filters.items():
        db_col = api_to_db.get(api_field)
        if db_col and hasattr(RetailPrice, db_col):
            stmt = stmt.where(getattr(RetailPrice, db_col) == value)

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [_row_to_api_dict(row) for row in rows]
