"""VM productName parser — extracts os, deployment, series, category sub-dimensions.

Handles all known Azure.cn VM productName patterns (~240 unique values):

| Pattern                                              | Example                                        |
|------------------------------------------------------|-------------------------------------------------|
| Virtual Machines {Series} Series [Windows]           | Virtual Machines Dv5 Series Windows             |
| {Series} Series Dedicated Host                       | DSv3 Series Dedicated Host                      |
| {Series} Series DedicatedHost (no space)             | Ddsv5 Series DedicatedHost                      |
| {Series} Series Cloud[  ]Services                    | Basv2 Series Cloud Services                     |
| lowercase "series"                                   | Virtual Machines DCadsv6 series                 |
| missing "Virtual Machines" prefix                    | Lasv3 Series Linux                              |
| "Basic" qualifier                                    | Virtual Machines A Series Basic                 |
| "Medium Memory" qualifier                            | Virtual Machines Mdsv3 Medium Memory Series Linux|
| "promo" in series name                               | Virtual Machines DSv2 promo Series              |
| special products                                     | Virtual Machines RI, Dedicated Host Reservation |
"""

import re
from dataclasses import dataclass

from .vm_category_map import get_vm_category

_SERIES_RE = re.compile(r"\b[Ss]eries\b")

_DEPLOYMENT_SUFFIXES = [
    " Dedicated Host",
    " DedicatedHost",
    " Cloud Services",
    " CloudServices",
]


@dataclass(frozen=True)
class VmParsedProduct:
    """Result of parsing a VM productName into sub-dimensions."""

    original: str
    os: str  # "Linux" | "Windows"
    deployment: str  # "Virtual Machines" | "Dedicated Host" | "Cloud Services"
    series: str | None  # "Dv5", "NCads A100 v4", "DSv2 promo", etc.
    category: str | None  # "General Purpose", "Memory Optimized", etc.
    tier: str | None  # "Basic" or None
    memory_profile: str | None  # "Medium Memory" or None
    special: str | None  # "RI", "Reservation", or None


def parse_vm_product_name(name: str) -> VmParsedProduct:
    """Parse a VM productName string into its constituent sub-dimensions.

    Algorithm:
    1. Strip OS suffix (" Windows" / " Linux") — default to Linux
    2. Check for special products (RI, Reservation)
    3. Detect deployment type from keywords
    4. Strip "Virtual Machines " prefix
    5. Strip deployment suffixes
    6. Extract qualifiers (Basic, Medium Memory)
    7. Strip "Series"/"series"
    8. Remaining text = series name
    9. Derive category from series via first-letter rules
    """
    original = name
    working = name

    # Step 1: OS detection — strip suffix
    if working.endswith(" Windows"):
        os_type = "Windows"
        working = working[: -len(" Windows")]
    elif working.endswith(" Linux"):
        os_type = "Linux"
        working = working[: -len(" Linux")]
    else:
        os_type = "Linux"

    # Step 2: Special products
    if working == "Virtual Machines RI":
        return VmParsedProduct(
            original=original,
            os=os_type,
            deployment="Virtual Machines",
            series=None,
            category=None,
            tier=None,
            memory_profile=None,
            special="RI",
        )
    if working == "Dedicated Host Reservation":
        return VmParsedProduct(
            original=original,
            os=os_type,
            deployment="Dedicated Host",
            series=None,
            category=None,
            tier=None,
            memory_profile=None,
            special="Reservation",
        )

    # Step 3: Deployment detection
    if "DedicatedHost" in working or "Dedicated Host" in working:
        deployment = "Dedicated Host"
    elif "CloudServices" in working or "Cloud Services" in working:
        deployment = "Cloud Services"
    else:
        deployment = "Virtual Machines"

    # Step 4: Strip "Virtual Machines " prefix
    if working.startswith("Virtual Machines "):
        working = working[len("Virtual Machines ") :]

    # Step 5: Strip deployment suffixes
    for suffix in _DEPLOYMENT_SUFFIXES:
        if working.endswith(suffix):
            working = working[: -len(suffix)]
            break

    # Step 6: Extract qualifiers
    tier = None
    memory_profile = None

    if " Basic" in working:
        tier = "Basic"
        working = working.replace(" Basic", "")

    if "Medium Memory" in working:
        memory_profile = "Medium Memory"
        working = working.replace("Medium Memory", "")

    # Step 7: Strip "Series" / "series" as a standalone word
    working = _SERIES_RE.sub("", working)

    # Step 8: Clean whitespace → series name
    series = " ".join(working.split()) or None

    # Step 9: Category from series
    category = get_vm_category(series) if series else None

    return VmParsedProduct(
        original=original,
        os=os_type,
        deployment=deployment,
        series=series,
        category=category,
        tier=tier,
        memory_profile=memory_profile,
        special=None,
    )
