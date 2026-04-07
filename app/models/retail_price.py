"""ORM model for CN retail prices (imported from ACN CSV data)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class RetailPrice(Base):
    """CN retail price row — one-to-one mapping with ACN CSV columns.

    Column naming: snake_case in DB, camelCase in CSV/API responses.
    The 20 CSV columns map directly to Global API field names.
    """

    __tablename__ = "retail_prices"

    # Surrogate PK (CSV has no natural single-column PK)
    id: Mapped[int] = mapped_column(primary_key=True)

    # --- Price fields ---
    currency_code: Mapped[str] = mapped_column(String(10), nullable=False, default="CNY")
    tier_minimum_units: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    retail_price: Mapped[float] = mapped_column(Float, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)

    # --- Location fields ---
    arm_region_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # --- Date ---
    effective_start_date: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Meter identity ---
    meter_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    meter_name: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Product identity ---
    product_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sku_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sku_name: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Service classification ---
    service_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    service_family: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # --- Unit and pricing type ---
    unit_of_measure: Mapped[str | None] = mapped_column(String(100), nullable=True)
    type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Optional fields ---
    arm_sku_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    term: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_primary_meter_region: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    __table_args__ = (
        # Query performance indexes matching common filter patterns
        Index("ix_rp_service_name", "service_name"),
        Index("ix_rp_arm_region_name", "arm_region_name"),
        Index("ix_rp_product_name", "product_name"),
        Index("ix_rp_sku_name", "sku_name"),
        Index("ix_rp_type", "type"),
        # Composite index for the most common cascade query pattern
        Index("ix_rp_service_region", "service_name", "arm_region_name"),
        Index(
            "ix_rp_cascade",
            "service_name", "arm_region_name", "product_name", "sku_name", "type",
        ),
    )


# camelCase CSV header → snake_case DB column mapping
CSV_TO_DB_COLUMNS: dict[str, str] = {
    "currencyCode": "currency_code",
    "tierMinimumUnits": "tier_minimum_units",
    "retailPrice": "retail_price",
    "unitPrice": "unit_price",
    "armRegionName": "arm_region_name",
    "location": "location",
    "effectiveStartDate": "effective_start_date",
    "meterId": "meter_id",
    "meterName": "meter_name",
    "productId": "product_id",
    "skuId": "sku_id",
    "productName": "product_name",
    "skuName": "sku_name",
    "serviceName": "service_name",
    "serviceFamily": "service_family",
    "unitOfMeasure": "unit_of_measure",
    "type": "type",
    "armSkuName": "arm_sku_name",
    "term": "term",
    "isPrimaryMeterRegion": "is_primary_meter_region",
}

# Reverse: snake_case DB column → camelCase API field
DB_TO_API_COLUMNS: dict[str, str] = {v: k for k, v in CSV_TO_DB_COLUMNS.items()}
