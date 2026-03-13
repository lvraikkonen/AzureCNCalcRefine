"""Pydantic schemas for the explore API endpoints."""

from pydantic import BaseModel


# ── service ───────────────────────────────────────────────────────────

class ValueCount(BaseModel):
    value: str
    count: int


class DimensionDistribution(BaseModel):
    name: str
    distinct_count: int
    top_values: list[ValueCount]


class ServiceResponse(BaseModel):
    service_name: str
    total_rows: int
    dimensions: list[DimensionDistribution]


# ── cascade ───────────────────────────────────────────────────────────

class CascadeSubDimension(BaseModel):
    field: str
    label: str
    options: list[str]
    selected: str | None = None
    order: int


class CascadeDimension(BaseModel):
    field: str
    label: str
    options: list[str]
    selected: str | None = None
    visible: bool = True
    sub_dimensions: list[CascadeSubDimension] | None = None


class CascadeRequest(BaseModel):
    service_name: str
    selections: dict[str, str] = {}
    sub_selections: dict[str, str] = {}


class CascadeResponse(BaseModel):
    service_name: str
    total_rows: int
    filtered_rows: int
    dimensions: list[CascadeDimension]


# ── meters ────────────────────────────────────────────────────────────

class PriceTier(BaseModel):
    tier_min_units: float
    unit_price: float
    retail_price: float


class MeterGroup(BaseModel):
    product: str
    sku: str
    meter: str
    type: str
    term: str
    unit: str
    is_reservation: bool
    tiers: list[PriceTier]


class MetersRequest(BaseModel):
    service_name: str
    region: str | None = None
    product: str | None = None
    sku: str | None = None
    raw: int | None = None


class MetersResponse(BaseModel):
    service_name: str
    total_rows: int
    groups: list[MeterGroup]
    raw_items: list[dict] | None = None


# ── productparse ──────────────────────────────────────────────────────

class ParsedProduct(BaseModel):
    product_name: str
    os: str
    deployment: str
    series: str | None
    category: str | None
    tier: str | None
    memory_profile: str | None
    special: str | None


class ProductParseRequest(BaseModel):
    service_name: str
    region: str | None = None
    product: str | None = None


class ProductParseResponse(BaseModel):
    service_name: str
    total_rows: int
    unique_products: int
    products: list[ParsedProduct]
    summary: dict
    unparsed: list[str]


# ── calculator ────────────────────────────────────────────────────────

class CalculatorItem(BaseModel):
    service_name: str
    region: str
    product: str
    sku: str
    type: str = "Consumption"
    term: str | None = None
    quantity: float = 1
    hours_per_month: float = 730


class MeterCost(BaseModel):
    meter: str
    unit: str
    tiers: list[PriceTier]
    usage: float
    monthly_cost: float


class CalculatorLineResult(BaseModel):
    input: CalculatorItem
    meters: list[MeterCost]
    monthly_cost: float
    payg_monthly_cost: float | None = None
    currency: str = "USD"


class CalculatorRequest(BaseModel):
    items: list[CalculatorItem]


class CalculatorResponse(BaseModel):
    items: list[CalculatorLineResult]
    total_monthly_cost: float
    currency: str = "USD"
