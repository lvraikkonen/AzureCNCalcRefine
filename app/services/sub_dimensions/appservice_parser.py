"""App Service productName parser — extracts os, tier sub-dimensions.

Handles Azure App Service productName patterns:

| productName                                        | tier              | os      |
|----------------------------------------------------|-------------------|---------|
| Azure App Service Basic Plan - Linux               | Basic             | Linux   |
| Azure App Service Standard Plan - Linux            | Standard          | Linux   |
| Azure App Service Premium v2 Plan                  | Premium V2        | Windows |
| Azure App Service Premium v3 Plan - Linux          | Premium V3        | Linux   |
| Azure App Service Premium v4 Plan                  | Premium V4        | Windows |
| Azure App Service Isolated Plan                    | Isolated          | Windows |
| Azure App Service Isolated v2 Plan - Linux         | Isolated V2       | Linux   |
| Azure App Service Premium Windows Container Plan   | Premium Container | Windows |
| Azure App Service Domain                           | (excluded)        |         |
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AppServiceParsedProduct:
    """Result of parsing an App Service productName into sub-dimensions."""

    original: str
    os: str        # "Linux" | "Windows"
    tier: str      # "Basic", "Standard", "Premium V2", etc.
    excluded: bool  # True for non-compute products like "Azure App Service Domain"


_PREFIX = "Azure App Service "

# Only these 8 tiers are valid compute plans — anything else is excluded
_VALID_TIERS = {
    "Basic", "Standard",
    "Premium V2", "Premium V3", "Premium V4",
    "Isolated", "Isolated V2",
    "Premium Container",
}


def parse_appservice_product_name(name: str) -> AppServiceParsedProduct:
    """Parse an App Service productName string into os and tier sub-dimensions."""
    original = name

    # Detect OS from " - Linux" suffix
    if name.endswith(" - Linux"):
        os_type = "Linux"
        working = name[: -len(" - Linux")]
    else:
        os_type = "Windows"
        working = name

    # Strip prefix "Azure App Service "
    if not working.startswith(_PREFIX):
        return AppServiceParsedProduct(
            original=original, os="", tier="", excluded=True,
        )
    working = working[len(_PREFIX):]

    # Strip trailing " Plan" if present
    if working.endswith(" Plan"):
        working = working[: -len(" Plan")]

    # Normalize tier: "Premium v2" → "Premium V2", "Isolated v2" → "Isolated V2"
    tier = re.sub(r"\bv(\d)", lambda m: f"V{m.group(1)}", working)

    # Handle "Premium Windows Container" → tier "Premium Container"
    tier = tier.replace("Premium Windows Container", "Premium Container")

    # Exclude anything that doesn't map to a known compute tier
    if tier not in _VALID_TIERS:
        return AppServiceParsedProduct(
            original=original, os="", tier="", excluded=True,
        )

    return AppServiceParsedProduct(
        original=original, os=os_type, tier=tier, excluded=False,
    )
