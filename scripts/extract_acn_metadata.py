"""
Extract structured metadata from the ACN calculator JSON.

Usage: python scripts/extract_acn_metadata.py

Input:  prod-config/calculatordatamodel.json (from convert_acn_datamodel.js)
Output:
  data/acn_product_names.json          - slug -> Chinese name + region constraints
  data/acn_dimension_templates/        - per-service dimension structure + suggested config
  data/acn_price_validation.json       - known CNY prices for validation
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROD_CONFIG = ROOT / "prod-config"
DATA = ROOT / "data"
TEMPLATES_DIR = DATA / "acn_dimension_templates"

# Region text -> standardized code
REGION_MAP = {
    "中国东部3": "chinaeast3",
    "中国东部2": "chinaeast2",
    "中国东部1": "chinaeast",
    "中国东部": "chinaeast",
    "中国北部3": "chinanorth3",
    "中国北部2": "chinanorth2",
    "中国北部1": "chinanorth",
    "中国北部": "chinanorth",
}

# Regex: match "仅适用于" or "仅支持" followed by region names
REGION_CONSTRAINT_RE = re.compile(
    r"\s*[-–—]\s*仅(?:适用于|支持)(.*?)$"
)

# Known tier names in Chinese
TIER_NAMES = {"免费", "基本", "标准", "高级", "共享", "专用", "隔离", "高级版", "标准版", "免费版"}


def parse_region_constraints(name: str) -> tuple[str, list[str] | None]:
    """Extract region constraints from name, return (clean_name, constraints)."""
    m = REGION_CONSTRAINT_RE.search(name)
    if not m:
        return name.strip(), None

    clean_name = name[: m.start()].strip()
    region_text = m.group(1).strip()

    regions = []
    # Sort by longest match first to avoid partial matches
    for text, code in sorted(REGION_MAP.items(), key=lambda x: -len(x[0])):
        if text in region_text:
            regions.append(code)
            region_text = region_text.replace(text, "")

    return clean_name, sorted(set(regions)) if regions else None


def classify_types_semantic(types: list[dict]) -> str:
    """Classify Types[] semantic pattern."""
    if len(types) == 1:
        name = types[0].get("Name", "")
        if name.lower() == "default" or name == types[0].get("Name", ""):
            return "single"
        return "service"

    names = {t["Name"] for t in types}
    if names & TIER_NAMES:
        return "tier"
    if all(t["Name"].lower() == "default" for t in types):
        return "default"
    return "category"


def classify_features_semantic(features: list[dict]) -> str:
    """Classify Features[] semantic pattern."""
    if len(features) == 1 and features[0].get("Name", "").lower() == "default":
        return "default"
    if all(f.get("Name", "").lower() == "default" for f in features):
        return "default"
    return "named_meter"


def suggest_quantity_model(types: list[dict]) -> str:
    """Derive quantity_model from structure."""
    all_default_features = True
    all_hourly = True
    has_named_features = False

    for t in types:
        for f in t.get("Features", []):
            if f.get("Name", "").lower() != "default":
                has_named_features = True
                all_default_features = False
            period = f.get("PricePeriod", "0")
            if period == "1":  # Monthly
                all_hourly = False

    if all_default_features and all_hourly:
        return "instances_x_hours"
    return "per_meter"


def suggest_config(slug: str, types: list[dict], types_semantic: str) -> dict:
    """Generate suggested service_config fields."""
    config = {}

    config["quantity_model"] = suggest_quantity_model(types)

    # dimension_labels
    if types_semantic == "tier":
        config["dimension_labels"] = {"skuName": "Tier"}

    # hidden_dimensions: suggest hiding productName for simple products
    if types_semantic in ("single", "default"):
        config["hidden_dimensions"] = ["productName"]

    return config


def parse_price_tier(price_tier: str, price_per_tier: str) -> list[dict]:
    """Parse PriceTier/PricePerTier into structured price entries."""
    prices = []

    if price_tier == "0":  # Free
        prices.append({"type": "free", "price": 0})
    elif price_tier == "-2":  # Fixed
        try:
            prices.append({"type": "fixed", "price": float(price_per_tier)})
        except (ValueError, TypeError):
            pass
    elif price_tier == "-1":  # Linear
        try:
            prices.append({"type": "linear", "price": float(price_per_tier)})
        except (ValueError, TypeError):
            pass
    else:
        # Tiered: parse min/max pairs and per-tier prices
        try:
            boundaries = [float(x) for x in price_tier.split(",")]
            tier_prices = [float(x) for x in price_per_tier.split(",")]
            for i, tp in enumerate(tier_prices):
                tier_entry = {"type": "tiered", "tier_index": i, "price": tp}
                # boundaries come in min,max pairs
                if i * 2 < len(boundaries):
                    tier_entry["min_units"] = boundaries[i * 2]
                if i * 2 + 1 < len(boundaries):
                    tier_entry["max_units"] = boundaries[i * 2 + 1]
                prices.append(tier_entry)
        except (ValueError, TypeError):
            pass

    return prices


def extract_prices(slug: str, types: list[dict]) -> list[dict]:
    """Extract all price points from a service."""
    prices = []
    for t in types:
        for f in t.get("Features", []):
            period = "hourly" if f.get("PricePeriod", "0") == "0" else "monthly"
            unit = f.get("PriceUnit", "")
            for s in f.get("Sizes", []):
                tier_data = parse_price_tier(
                    str(s.get("PriceTier", "")),
                    str(s.get("PricePerTier", ""))
                )
                for td in tier_data:
                    prices.append({
                        "type_name": t["Name"],
                        "feature_name": f["Name"],
                        "size_name": s.get("Name", ""),
                        "period": period,
                        "unit": unit,
                        **td,
                    })
    return prices


def main():
    datamodel_path = PROD_CONFIG / "calculatordatamodel.json"
    data = json.loads(datamodel_path.read_text("utf-8"))
    services = data.get("Services", {})

    product_names = {}
    price_validation = {}

    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    for slug, svc in services.items():
        raw_name = svc.get("Name", slug)
        clean_name, region_constraints = parse_region_constraints(raw_name)

        # --- Product names ---
        product_names[slug] = {
            "display_name_raw": raw_name,
            "display_name_clean": clean_name,
            "region_constraints": region_constraints,
        }

        # --- Dimension templates ---
        types = svc.get("Types", [])
        types_semantic = classify_types_semantic(types)

        type_entries = []
        for t in types:
            features = t.get("Features", [])
            features_semantic = classify_features_semantic(features)

            feature_entries = []
            for f in features:
                feature_name, f_regions = parse_region_constraints(f.get("Name", ""))
                feature_entry = {
                    "name": feature_name,
                    "price_period": "hourly" if f.get("PricePeriod", "0") == "0" else "monthly",
                    "sizes_count": len(f.get("Sizes", [])),
                }
                if f_regions:
                    feature_entry["region_constraints"] = f_regions
                if f.get("PriceUnit"):
                    feature_entry["price_unit"] = f["PriceUnit"]
                feature_entries.append(feature_entry)

            type_name, t_regions = parse_region_constraints(t.get("Name", ""))
            type_entry = {
                "name": type_name,
                "features_semantic": features_semantic,
                "features": feature_entries,
            }
            if t_regions:
                type_entry["region_constraints"] = t_regions
            type_entries.append(type_entry)

        template = {
            "slug": slug,
            "display_name": clean_name,
            "types_semantic": types_semantic,
            "types": type_entries,
            "suggested_config": suggest_config(slug, types, types_semantic),
        }

        template_path = TEMPLATES_DIR / f"{slug}.json"
        template_path.write_text(json.dumps(template, ensure_ascii=False, indent=2), "utf-8")

        # --- Price validation ---
        prices = extract_prices(slug, types)
        if prices:
            price_validation[slug] = {
                "currency": "CNY",
                "display_name": clean_name,
                "prices": prices,
            }

    # Write product names
    names_path = DATA / "acn_product_names.json"
    names_path.write_text(json.dumps(product_names, ensure_ascii=False, indent=2), "utf-8")

    # Write price validation
    prices_path = DATA / "acn_price_validation.json"
    prices_path.write_text(json.dumps(price_validation, ensure_ascii=False, indent=2), "utf-8")

    # Summary
    with_regions = sum(1 for v in product_names.values() if v["region_constraints"])
    total_prices = sum(len(v["prices"]) for v in price_validation.values())

    print(f"Extracted {len(product_names)} product names ({with_regions} with region constraints)")
    print(f"Generated {len(product_names)} dimension templates in {TEMPLATES_DIR}")
    print(f"Extracted {total_prices} price entries across {len(price_validation)} products")
    print(f"\nOutput files:")
    print(f"  {names_path}")
    print(f"  {TEMPLATES_DIR}/")
    print(f"  {prices_path}")


if __name__ == "__main__":
    main()
