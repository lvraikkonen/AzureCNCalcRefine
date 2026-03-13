"""VM series to category mapping using Azure naming conventions.

Uses first-letter rules derived from Azure VM naming standards:
- D-family → General Purpose
- E-family → Memory Optimized
- F-family → Compute Optimized
- N-family → GPU
- etc.

Multi-character prefixes are checked first to handle special sub-families
(DC, EC, NC, NV, ND, HB, HC).
"""

# Override dict for exceptions to the first-letter rule.
# Currently empty — add entries here if a series breaks the naming convention.
CATEGORY_OVERRIDES: dict[str, str] = {}

_SINGLE_CHAR_MAP: dict[str, str] = {
    "A": "General Purpose",
    "B": "General Purpose",
    "D": "General Purpose",
    "E": "Memory Optimized",
    "F": "Compute Optimized",
    "H": "High Performance Compute",
    "L": "Storage Optimized",
    "M": "Memory Optimized",
    "N": "GPU",
}


def get_vm_category(series: str) -> str:
    """Derive the VM category from a series name (e.g. 'Dv5' → 'General Purpose').

    Lookup order:
    1. CATEGORY_OVERRIDES (explicit exceptions)
    2. Multi-character prefix rules
    3. Single-character first-letter rules
    4. Fallback → 'Other'
    """
    if not series:
        return "Other"

    if series in CATEGORY_OVERRIDES:
        return CATEGORY_OVERRIDES[series]

    upper = series.upper()

    # Multi-character prefixes (check before single-char)
    if upper.startswith("DC"):
        return "General Purpose"
    if upper.startswith("EC"):
        return "Memory Optimized"
    if upper.startswith(("NC", "NV", "ND")):
        return "GPU"
    if upper.startswith(("HB", "HC")):
        return "High Performance Compute"

    # Single-character first-letter
    return _SINGLE_CHAR_MAP.get(upper[0], "Other")
