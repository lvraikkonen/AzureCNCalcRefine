"""Sub-dimension parser registry.

Maps service_name → parser instance. When the configurations API returns
options for a dimension that has a registered parser, the parser extracts
sub-dimension metadata for frontend filtering.

Currently supported:
- "Virtual Machines" → VmProductNameParser (parses productName → os, deployment, tier, category, instance_series)
"""

from .base import SubDimensionDef, SubDimensionParser
from .vm_parser import VmParsedProduct, parse_vm_product_name

from app.schemas.configuration import SubDimension


class VmProductNameParser(SubDimensionParser):
    """Extracts os/deployment/category/instance_series from VM productName values."""

    _SUB_DIMS = [
        SubDimensionDef(field="os", label="Operating System", attr="os", order=0),
        SubDimensionDef(
            field="deployment", label="Deployment", attr="deployment", order=1
        ),
        SubDimensionDef(field="tier", label="Tier", attr="tier", order=2),
        SubDimensionDef(field="category", label="Category", attr="category", order=3),
        SubDimensionDef(
            field="instance_series",
            label="Instance Series",
            attr="series",
            order=4,
        ),
    ]

    def target_field(self) -> str:
        return "product_name"

    def parse(self, value: str) -> VmParsedProduct:
        return parse_vm_product_name(value)

    def sub_dimension_definitions(self) -> list[SubDimensionDef]:
        return self._SUB_DIMS

    def is_excluded(self, parsed: object) -> bool:
        return isinstance(parsed, VmParsedProduct) and parsed.special is not None

    def normalize_value(self, field: str, raw_value: object) -> str | None:
        if field == "tier":
            # VmParsedProduct.tier is "Basic" or None; map None → "Standard"
            return str(raw_value) if raw_value is not None else "Standard"
        if raw_value is None:
            return None
        return str(raw_value)


# ── Registry ──────────────────────────────────────────────────────────

_REGISTRY: dict[str, SubDimensionParser] = {
    "Virtual Machines": VmProductNameParser(),
}


def get_sub_dimension_parser(service_name: str) -> SubDimensionParser | None:
    """Look up the sub-dimension parser for a service, or None if not configured."""
    return _REGISTRY.get(service_name)
