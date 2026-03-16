"""Explore API — exposes Azure Global Retail Prices data for frontend interaction.

Five endpoint groups mirroring the explore CLI tool:
- service:      dimension distribution summary
- cascade:      cascading filter with sub-dimension support
- meters:       meter/tier pricing details
- productparse: VM productName sub-dimension parsing
- calculator:   price calculation based on selections + quantity
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

from fastapi import APIRouter

from app.schemas.explore import (
    CalculatorItem,
    CalculatorLineResult,
    CalculatorRequest,
    CalculatorResponse,
    CascadeDimension,
    CascadeRequest,
    CascadeResponse,
    CascadeSubDimension,
    DimensionDistribution,
    MeterCost,
    MeterGroup,
    MetersRequest,
    MetersResponse,
    ParsedProduct,
    PriceTier,
    ProductParseRequest,
    ProductParseResponse,
    ServiceResponse,
    ValueCount,
)
from app.services.global_pricing import (
    build_api_filters,
    calculate_tiered_cost,
    fetch_global_prices,
    filter_primary_non_devtest,
    get_effective_term,
)
from app.services.sub_dimensions import get_sub_dimension_parser

router = APIRouter(prefix="/api/v1/explore", tags=["explore"])

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config" / "service_configs"


def _load_service_config(service_name: str) -> dict | None:
    """Load the JSON config file for a service, or None if not found."""
    slug = service_name.lower().replace(" ", "_")
    config_path = _CONFIG_DIR / f"{slug}.json"
    if not config_path.exists():
        return None
    return json.loads(config_path.read_text(encoding="utf-8"))


def _resolve_api_service_name(service_name: str) -> str:
    """Return the Azure API serviceName for a given catalog service name.

    Some services have a mismatch between the catalog name and the API
    filter value (e.g. catalog "App Service" → API "Azure App Service").
    Falls back to service_name if no mapping is configured.
    """
    config = _load_service_config(service_name)
    if config and "api_service_name" in config:
        return config["api_service_name"]
    return service_name


# ═══════════════════════════════════════════════════════════════════════
# 0. SERVICE CONFIG — default selections for a service
# ═══════════════════════════════════════════════════════════════════════

@router.get("/service-config/{service_name}")
async def get_service_config(service_name: str):
    """Return default configuration for a service (selections, sub_selections, etc.)."""
    config = _load_service_config(service_name)
    if not config:
        return {"service_name": service_name, "defaults": {}}

    # Derive static_subs and hidden_subs from sub_dimensions config
    sub_dims_config = config.get("sub_dimensions", {})
    all_sub_fields = [d["field"] for d in sub_dims_config.get("dimensions", [])]
    # For VM: os, tier, category are static; deployment is hidden; instance_series is dynamic
    # For App Service: os, tier are static (all 2 dims); nothing hidden
    # Convention: sub-dims with order < (total - 1) that aren't hidden are static
    # Use explicit lists from config if present, otherwise derive sensible defaults
    static_subs = config.get("static_subs", all_sub_fields)
    hidden_subs = config.get("hidden_subs", [])

    return {
        "service_name": service_name,
        "defaults": config.get("defaults", {}),
        "quantity_label": config.get("quantity_label", "VMs"),
        "static_subs": static_subs,
        "hidden_subs": hidden_subs,
    }


# ── Cascade dimension definitions ────────────────────────────────────

CASCADE_DIMS = [
    ("armRegionName", "Region"),
    ("productName", "Product"),
    ("skuName", "SKU"),
    ("type", "Pricing Type"),
    ("term", "Term"),
]


# ── helpers ───────────────────────────────────────────────────────────

def _matches_sub_selections(
    product_name: str,
    parser,
    sub_selections: dict[str, str],
) -> bool:
    """Check if a productName matches all sub_selections via the parser."""
    parsed = parser.parse(product_name)
    if parser.is_excluded(parsed):
        return False
    for field, value in sub_selections.items():
        sd_def = next(
            (sd for sd in parser.sub_dimension_definitions() if sd.field == field),
            None,
        )
        if sd_def:
            actual = parser.normalize_value(field, getattr(parsed, sd_def.attr, None))
            if actual != value:
                return False
    return True


def _collect_options(items: list[dict], field: str) -> list[str]:
    """Collect sorted unique values for a dimension field."""
    if field == "term":
        return sorted({get_effective_term(i) for i in items if get_effective_term(i)})
    return sorted({i.get(field, "") for i in items if i.get(field)})


# ═══════════════════════════════════════════════════════════════════════
# 1. SERVICE — dimension distribution summary
# ═══════════════════════════════════════════════════════════════════════

@router.get("/service/{service_name}", response_model=ServiceResponse)
async def explore_service(service_name: str, region: str | None = None):
    """按服务查询各维度值域分布（不过滤 isPrimaryMeterRegion）。"""
    api_name = _resolve_api_service_name(service_name)
    filters = build_api_filters(api_name, region=region)
    items = await fetch_global_prices(filters)

    dim_names = ["productName", "skuName", "type", "term", "unitOfMeasure"]
    dimensions = []
    for dim in dim_names:
        if dim == "term":
            counter = Counter(get_effective_term(i) or "(empty)" for i in items)
        else:
            counter = Counter(i.get(dim, "(empty)") for i in items)

        top = [ValueCount(value=str(v), count=c) for v, c in counter.most_common(30)]
        dimensions.append(DimensionDistribution(
            name=dim,
            distinct_count=len(counter),
            top_values=top,
        ))

    return ServiceResponse(
        service_name=service_name,
        total_rows=len(items),
        dimensions=dimensions,
    )


# ═══════════════════════════════════════════════════════════════════════
# 2. CASCADE — cascading filter with sub-dimensions
# ═══════════════════════════════════════════════════════════════════════

@router.post("/cascade", response_model=CascadeResponse)
async def explore_cascade(req: CascadeRequest):
    """级联筛选：返回各维度可选值，支持 VM 子维度（os/tier/category/series）。

    每次用户变更选择后，前端重新调用此接口获取更新后的选项。
    """
    # Build API-level filters — pass selected dimensions to avoid 10k-row truncation
    api_name = _resolve_api_service_name(req.service_name)
    api_filters = build_api_filters(
        api_name,
        region=req.selections.get("armRegionName"),
        product=req.selections.get("productName"),
        sku=req.selections.get("skuName"),
    )
    items = await fetch_global_prices(api_filters)
    total_rows = len(items)
    items = filter_primary_non_devtest(items)
    filtered_rows = len(items)

    # Sub-dimension parser (if available for this service)
    parser = get_sub_dimension_parser(req.service_name)

    # Pre-compute valid productNames from sub_selections
    valid_pnames: set[str] | None = None
    if req.sub_selections and parser:
        all_pnames = {i.get("productName", "") for i in items if i.get("productName")}
        valid_pnames = {
            pn for pn in all_pnames
            if _matches_sub_selections(pn, parser, req.sub_selections)
        }

    dimensions: list[CascadeDimension] = []
    for field, label in CASCADE_DIMS:
        # Filter by all OTHER main selections (cascade algorithm)
        filtered = items
        for other_field, _ in CASCADE_DIMS:
            if other_field != field and other_field in req.selections:
                sel_val = req.selections[other_field]
                if other_field == "term":
                    filtered = [i for i in filtered if get_effective_term(i) == sel_val]
                else:
                    filtered = [i for i in filtered if i.get(other_field) == sel_val]

        # For non-productName dims, also apply sub_selection constraint
        if field != "productName" and valid_pnames is not None:
            filtered = [i for i in filtered if i.get("productName") in valid_pnames]

        options = _collect_options(filtered, field)

        # Visibility: term only visible when type is Reservation/SavingsPlan
        visible = True
        if field == "term":
            sel_type = req.selections.get("type")
            visible = sel_type in ("Reservation", "SavingsPlanConsumption")

        dim = CascadeDimension(
            field=field,
            label=label,
            options=options,
            selected=req.selections.get(field),
            visible=visible,
        )

        # Sub-dimensions for productName
        if field == "productName" and parser:
            sub_dims = parser.extract_sub_dimensions(
                options,
                current_sub_selections=req.sub_selections or {},
            )
            dim.sub_dimensions = [
                CascadeSubDimension(
                    field=sd.field,
                    label=sd.label,
                    options=[o.value for o in sd.options],
                    selected=sd.selected,
                    order=sd.order,
                )
                for sd in sub_dims
            ]
            # Filter productName options by sub_selections
            if valid_pnames is not None:
                dim.options = sorted(pn for pn in options if pn in valid_pnames)

        dimensions.append(dim)

    return CascadeResponse(
        service_name=req.service_name,
        total_rows=total_rows,
        filtered_rows=filtered_rows,
        dimensions=dimensions,
    )


# ═══════════════════════════════════════════════════════════════════════
# 3. METERS — meter/tier pricing details
# ═══════════════════════════════════════════════════════════════════════

@router.post("/meters", response_model=MetersResponse)
async def explore_meters(req: MetersRequest):
    """查看具体配置的 meter 分层定价结构。"""
    api_name = _resolve_api_service_name(req.service_name)
    filters = build_api_filters(
        api_name, region=req.region, product=req.product, sku=req.sku,
    )
    items = await fetch_global_prices(filters)

    # Group by (meterName, type, effectiveTerm)
    meter_groups: dict[tuple, list[dict]] = defaultdict(list)
    for item in items:
        key = (
            item.get("meterName", ""),
            item.get("type", ""),
            get_effective_term(item),
        )
        meter_groups[key].append(item)

    groups = []
    for (meter, typ, term), rows in sorted(meter_groups.items()):
        tiers = sorted(rows, key=lambda r: float(r.get("tierMinimumUnits", 0)))
        groups.append(MeterGroup(
            product=rows[0].get("productName", ""),
            sku=rows[0].get("skuName", ""),
            meter=meter,
            type=typ,
            term=term or "-",
            unit=rows[0].get("unitOfMeasure", ""),
            is_reservation=typ == "Reservation",
            tiers=[
                PriceTier(
                    tier_min_units=float(r.get("tierMinimumUnits", 0)),
                    unit_price=float(r.get("unitPrice", 0)),
                    retail_price=float(r.get("retailPrice", 0)),
                )
                for r in tiers
            ],
        ))

    raw_items = items[: req.raw] if req.raw else None

    return MetersResponse(
        service_name=req.service_name,
        total_rows=len(items),
        groups=groups,
        raw_items=raw_items,
    )


# ═══════════════════════════════════════════════════════════════════════
# 4. PRODUCTPARSE — VM productName sub-dimension parsing
# ═══════════════════════════════════════════════════════════════════════

@router.post("/productparse", response_model=ProductParseResponse)
async def explore_productparse(req: ProductParseRequest):
    """使用 vm_parser 解析 productName，展示子维度拆解结果。"""
    from app.services.sub_dimensions.vm_parser import parse_vm_product_name

    api_name = _resolve_api_service_name(req.service_name)
    filters = build_api_filters(
        api_name, region=req.region, product=req.product,
    )
    items = await fetch_global_prices(filters)

    product_names = sorted(
        {i.get("productName", "") for i in items if i.get("productName")}
    )

    products = []
    unparsed = []
    os_counter: Counter[str] = Counter()
    deploy_counter: Counter[str] = Counter()
    category_counter: Counter[str | None] = Counter()

    for pn in product_names:
        parsed = parse_vm_product_name(pn)
        os_counter[parsed.os] += 1
        deploy_counter[parsed.deployment] += 1
        category_counter[parsed.category] += 1

        if parsed.series is None and parsed.special is None:
            unparsed.append(pn)

        products.append(ParsedProduct(
            product_name=pn,
            os=parsed.os,
            deployment=parsed.deployment,
            series=parsed.series,
            category=parsed.category,
            tier=parsed.tier,
            memory_profile=parsed.memory_profile,
            special=parsed.special,
        ))

    return ProductParseResponse(
        service_name=req.service_name,
        total_rows=len(items),
        unique_products=len(product_names),
        products=products,
        summary={
            "os": dict(os_counter.most_common()),
            "deployment": dict(deploy_counter.most_common()),
            "category": dict(category_counter.most_common()),
        },
        unparsed=unparsed,
    )


# ═══════════════════════════════════════════════════════════════════════
# 5. CALCULATOR — price calculation
# ═══════════════════════════════════════════════════════════════════════

async def _calculate_one(item: CalculatorItem) -> CalculatorLineResult:
    """Calculate monthly cost for a single configuration."""
    api_name = _resolve_api_service_name(item.service_name)
    filters = build_api_filters(
        api_name,
        region=item.region,
        product=item.product,
        sku=item.sku,
    )
    all_items = await fetch_global_prices(filters)

    # Filter to matching type
    matched = [i for i in all_items if i.get("type") == item.type]

    # Filter to matching term (for Reservation / SavingsPlan)
    if item.term:
        matched = [i for i in matched if get_effective_term(i) == item.term]

    # Group by meterName
    meter_groups: dict[str, list[dict]] = defaultdict(list)
    for row in matched:
        meter_groups[row.get("meterName", "")].append(row)

    meter_costs: list[MeterCost] = []
    total = 0.0

    for meter_name, rows in sorted(meter_groups.items()):
        tiers = sorted(rows, key=lambda r: float(r.get("tierMinimumUnits", 0)))
        unit = rows[0].get("unitOfMeasure", "")

        tier_models = [
            PriceTier(
                tier_min_units=float(r.get("tierMinimumUnits", 0)),
                unit_price=float(r.get("unitPrice", 0)),
                retail_price=float(r.get("retailPrice", 0)),
            )
            for r in tiers
        ]

        # Determine usage based on unit type
        if item.type == "Reservation":
            # Reservation: unitPrice is total for the term, per instance
            usage = item.quantity
            cost = float(tiers[0].get("unitPrice", 0)) * item.quantity
        elif unit == "1 Hour":
            # Per-hour pricing: usage = hours × instances
            usage = item.hours_per_month * item.quantity
            cost = calculate_tiered_cost(tiers, usage)
        else:
            # Other units: usage = quantity directly
            usage = item.quantity
            cost = calculate_tiered_cost(tiers, usage)

        meter_costs.append(MeterCost(
            meter=meter_name,
            unit=unit,
            tiers=tier_models,
            usage=usage,
            monthly_cost=round(cost, 6),
        ))
        total += cost

    # Compute PAYG baseline for discount comparison
    payg_monthly_cost = None
    if item.type != "Consumption":
        consumption_rows = [i for i in all_items if i.get("type") == "Consumption"]
        if consumption_rows:
            payg_groups: dict[str, list[dict]] = defaultdict(list)
            for row in consumption_rows:
                payg_groups[row.get("meterName", "")].append(row)
            payg_total = 0.0
            for _, rows in payg_groups.items():
                tiers = sorted(rows, key=lambda r: float(r.get("tierMinimumUnits", 0)))
                unit = rows[0].get("unitOfMeasure", "")
                if unit == "1 Hour":
                    payg_total += calculate_tiered_cost(
                        tiers, item.hours_per_month * item.quantity,
                    )
                else:
                    payg_total += calculate_tiered_cost(tiers, item.quantity)
            payg_monthly_cost = round(payg_total, 6)

    return CalculatorLineResult(
        input=item,
        meters=meter_costs,
        monthly_cost=round(total, 6),
        payg_monthly_cost=payg_monthly_cost,
        currency="USD",
    )


@router.post("/calculator", response_model=CalculatorResponse)
async def explore_calculator(req: CalculatorRequest):
    """根据用户选择的配置和用量计算月度费用。

    - Consumption (1 Hour): unitPrice × hours_per_month × quantity
    - Reservation: unitPrice × quantity (unitPrice 为承诺期总价)
    - Tiered pricing: 按阶梯累进计算
    """
    results = []
    for item in req.items:
        result = await _calculate_one(item)
        results.append(result)

    return CalculatorResponse(
        items=results,
        total_monthly_cost=round(sum(r.monthly_cost for r in results), 6),
        currency="USD",
    )
