"""Abstract base class for sub-dimension parsers.

Each service that needs sub-dimension extraction implements a parser
that knows how to decompose compound dimension values (e.g. productName,
skuName) into independent sub-dimensions for frontend filtering.

The main cascade query (5 dimensions) remains unchanged. Sub-dimensions
are computed in-memory from the options list returned by the cascade.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.schemas.configuration import SubDimension, SubDimensionOption


@dataclass(frozen=True)
class SubDimensionDef:
    """Definition of a single sub-dimension for extraction."""

    field: str  # API field name, e.g. "os"
    label: str  # Display label, e.g. "Operating System"
    attr: str  # Attribute name on the parsed product, e.g. "os"
    order: int  # Display order


class SubDimensionParser(ABC):
    """Abstract parser that extracts sub-dimensions from a cascade dimension's options."""

    @abstractmethod
    def target_field(self) -> str:
        """The cascade dimension field this parser applies to (e.g. 'product_name')."""
        ...

    @abstractmethod
    def parse(self, value: str) -> object:
        """Parse a single option value into a structured result with sub-dimension attributes."""
        ...

    @abstractmethod
    def sub_dimension_definitions(self) -> list[SubDimensionDef]:
        """Return the ordered list of sub-dimension definitions."""
        ...

    def is_excluded(self, parsed: object) -> bool:
        """Return True if this parsed product should be excluded from sub-dimension filtering.

        Override to exclude special products (e.g. RI, Reservation).
        """
        return False

    def normalize_value(self, field: str, raw_value: object) -> str | None:
        """Normalize a parsed attribute value for display.

        Override to map internal representations to user-facing labels,
        e.g. tier=None → "Standard".  Return None to exclude the value.
        """
        if raw_value is None:
            return None
        return str(raw_value)

    def extract_sub_dimensions(
        self,
        options: list[str],
        current_sub_selections: dict[str, str] | None = None,
    ) -> list[SubDimension]:
        """Extract sub-dimension metadata from a list of option values.

        Applies in-memory cascading: for each sub-dimension, filters parsed
        products by all *other* selected sub-dimensions to compute available
        options. This mirrors the main cascade algorithm but runs in memory.

        Args:
            options: List of raw option values (e.g. productName strings).
            current_sub_selections: Currently selected sub-dimension values,
                e.g. {"os": "Linux", "category": "General Purpose"}.

        Returns:
            List of SubDimension objects with cascaded option lists.
        """
        if current_sub_selections is None:
            current_sub_selections = {}

        # Parse all options and exclude specials
        parsed_items = []
        for opt in options:
            p = self.parse(opt)
            if not self.is_excluded(p):
                parsed_items.append((opt, p))

        sub_defs = self.sub_dimension_definitions()

        result: list[SubDimension] = []
        for sd in sub_defs:
            # Filter by all OTHER selected sub-dimensions (in-memory cascade)
            filtered = parsed_items
            for other_sd in sub_defs:
                if other_sd.field != sd.field and other_sd.field in current_sub_selections:
                    sel_val = current_sub_selections[other_sd.field]
                    filtered = [
                        (opt, p)
                        for opt, p in filtered
                        if self.normalize_value(other_sd.field, getattr(p, other_sd.attr, None)) == sel_val
                    ]

            # Collect unique values for this sub-dimension
            values = sorted(
                v
                for v in {
                    self.normalize_value(sd.field, getattr(p, sd.attr, None))
                    for _, p in filtered
                }
                if v is not None
            )

            result.append(
                SubDimension(
                    field=sd.field,
                    label=sd.label,
                    options=[SubDimensionOption(value=v) for v in values],
                    selected=current_sub_selections.get(sd.field),
                    order=sd.order,
                )
            )

        return result
