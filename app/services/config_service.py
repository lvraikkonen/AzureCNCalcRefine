"""Configuration service — cascading filter logic with sub-dimension enrichment.

Core algorithm:
1. Standard 5-dimension cascade query (SQL) — unchanged
2. Sub-dimension enrichment (in-memory) — new

The cascade query returns available options for each dimension by applying
all *other* selected dimensions as filters. Sub-dimensions are then extracted
from the options of the target dimension (e.g. product_name for VMs) using
a registered parser.
"""

from app.schemas.configuration import (
    ConfigurationResponse,
    DimensionResponse,
)
from app.services.sub_dimensions import get_sub_dimension_parser

# Dimension order for the cascade filter
DIMENSION_ORDER = [
    ("arm_region_name", "Region"),
    ("product_name", "Product"),
    ("sku_name", "SKU / Size"),
    ("type", "Pricing Model"),
    ("term", "Term"),
]


async def get_configurations(
    service_name: str,
    selections: dict[str, str] | None = None,
    sub_selections: dict[str, dict[str, str]] | None = None,
) -> ConfigurationResponse:
    """Get cascaded dimension options for a service, with optional sub-dimensions.

    Args:
        service_name: The Azure service name (e.g. "Virtual Machines").
        selections: Current user selections for the 5 cascade dimensions.
        sub_selections: Sub-dimension selections keyed by parent dimension field,
            e.g. {"product_name": {"os": "Linux", "category": "General Purpose"}}.

    Returns:
        ConfigurationResponse with dimension options and sub-dimension metadata.
    """
    if selections is None:
        selections = {}
    if sub_selections is None:
        sub_selections = {}

    # Step 1: Standard 5-dimension cascade (database query)
    # TODO: implement with SQLAlchemy when database layer is ready
    dimensions = await _cascade_query(service_name, selections)

    # Step 2: Sub-dimension enrichment (in-memory, < 1ms)
    parser = get_sub_dimension_parser(service_name)
    if parser:
        target = parser.target_field()
        for dim in dimensions:
            if dim.field == target:
                dim.sub_dimensions = parser.extract_sub_dimensions(
                    dim.options,
                    current_sub_selections=sub_selections.get(target, {}),
                )

    return ConfigurationResponse(service_name=service_name, dimensions=dimensions)


async def _cascade_query(
    service_name: str,
    selections: dict[str, str],
) -> list[DimensionResponse]:
    """Execute the 5-dimension cascade filter against the database.

    For each dimension D, query DISTINCT values applying all other selected
    dimensions as filters (but not D itself).

    TODO: Replace this stub with actual SQLAlchemy queries when the database
    layer (models, engine, session) is implemented.
    """
    # Placeholder — returns empty dimensions until database is wired up
    dimensions = []
    for field, label in DIMENSION_ORDER:
        visible = True
        if field == "term":
            selected_type = selections.get("type")
            visible = selected_type in ("Reservation", "SavingsPlanConsumption")

        dimensions.append(
            DimensionResponse(
                field=field,
                label=label,
                options=[],  # populated by database query
                selected=selections.get(field),
                visible=visible,
            )
        )
    return dimensions
