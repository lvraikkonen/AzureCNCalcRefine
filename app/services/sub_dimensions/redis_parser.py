"""Redis Cache productName parser — extracts tier sub-dimension.

Handles Azure Redis Cache / Azure Managed Redis productName patterns:

| productName                              | tier                     |
|------------------------------------------|--------------------------|
| Azure Redis Cache Basic                  | Basic                    |
| Azure Redis Cache Standard               | Standard                 |
| Azure Redis Cache Premium                | Premium                  |
| Azure Redis Cache Enterprise             | Enterprise               |
| Azure Redis Cache Enterprise Flash       | Enterprise Flash         |
| Azure Redis Cache Isolated               | Isolated                 |
| Azure Managed Redis - Balanced           | Managed Balanced         |
| Azure Managed Redis - Compute Optimized  | Managed Compute Optimized|
| Azure Managed Redis - Flash Optimized    | Managed Flash Optimized  |
| Azure Managed Redis - Memory Optimized   | Managed Memory Optimized |
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RedisParsedProduct:
    """Result of parsing a Redis productName into sub-dimensions."""

    original: str
    tier: str       # "Basic", "Standard", "Premium", "Enterprise", etc.
    excluded: bool  # True for unrecognized patterns


_CACHE_PREFIX = "Azure Redis Cache "
_MANAGED_PREFIX = "Azure Managed Redis - "


def parse_redis_product_name(name: str) -> RedisParsedProduct:
    """Parse a Redis productName string into tier sub-dimension."""
    if name.startswith(_CACHE_PREFIX):
        tier = name[len(_CACHE_PREFIX):]
        return RedisParsedProduct(original=name, tier=tier, excluded=False)

    if name.startswith(_MANAGED_PREFIX):
        tier = "Managed " + name[len(_MANAGED_PREFIX):]
        return RedisParsedProduct(original=name, tier=tier, excluded=False)

    return RedisParsedProduct(original=name, tier="", excluded=True)
