"""
Generate draft service_config JSON files from ACN dimension templates.

Usage: python scripts/generate_service_configs.py [--batch 1|2|all] [--slug SLUG]

Input:  data/acn_dimension_templates/*.json  (from extract_acn_metadata.py)
        data/slug_to_service_name.json       (manual mapping)
        prod-config/calculatordatamodel.json  (raw legacy data for reference)
Output: data/generated_service_configs/*.json (for human review, NOT production)

Templates are generated based on 6 pricing patterns (A-F) and aligned with
the production service_config format used by app/config/service_configs/*.json.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "data" / "acn_dimension_templates"
OUTPUT_DIR = ROOT / "data" / "generated_service_configs"
EXISTING_DIR = ROOT / "app" / "config" / "service_configs"
NAMES_PATH = ROOT / "data" / "acn_product_names.json"
MAPPING_PATH = ROOT / "data" / "slug_to_service_name.json"
DATAMODEL_PATH = ROOT / "prod-config" / "calculatordatamodel.json"

# Chinese tier name -> English API skuName
TIER_CN_TO_EN = {
    "免费": "Free",
    "免费版": "Free",
    "基本": "Basic",
    "标准": "Standard",
    "标准版": "Standard",
    "高级": "Premium",
    "高级版": "Premium",
    "共享": "Shared",
    "专用": "Dedicated",
    "隔离": "Isolated",
}

PATTERN_NAMES = {
    "A": "instances_x_hours",
    "B": "per_meter",
    "C": "compute_plus_storage",
    "D": "resource_dimensions",
    "E": "sku_base_plus_meter",
    "F": "cross_service_composite",
}

# Batch definitions
BATCH_1 = [
    "redis-cache",
    "database-migration",
    "azure-ddos-protection",
    "azure-ddos-ipprotection",
    "managed-grafana",
    "azure-fluid-relay",
    "site-recovery",
    "notification-hub",
    "container-registry",
]

BATCH_2 = [
    "traffic-manager",
    "network-watcher",
    "ip-address",
    "application-gateway-standard-v2",
    "schedule",
]


def load_mapping() -> dict[str, dict]:
    if not MAPPING_PATH.exists():
        return {}
    data = json.loads(MAPPING_PATH.read_text("utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_datamodel() -> dict:
    if not DATAMODEL_PATH.exists():
        return {}
    data = json.loads(DATAMODEL_PATH.read_text("utf-8"))
    return data.get("Services", {})


def get_existing_configs() -> set[str]:
    existing = set()
    for p in EXISTING_DIR.glob("*.json"):
        try:
            cfg = json.loads(p.read_text("utf-8"))
            existing.add(cfg.get("service_name", ""))
        except (json.JSONDecodeError, KeyError):
            pass
    return existing


def build_legacy_reference(slug: str, raw_svc: dict | None) -> dict:
    """Build a reference section from raw legacy data for human review."""
    if not raw_svc:
        return {"slug": slug, "note": "Not found in legacy datamodel"}

    ref = {
        "slug": slug,
        "display_name_cn": raw_svc.get("Name", ""),
    }

    types = raw_svc.get("Types", [])
    type_summaries = []
    all_meters = []

    for t in types:
        tname = t.get("Name", "default")
        features = t.get("Features", [])
        feature_summaries = []

        for f in features:
            fname = f.get("Name", "default")
            period = "hourly" if f.get("PricePeriod", "0") == "0" else "monthly"
            sizes = f.get("Sizes", [])
            price_unit = f.get("PriceUnit", "")

            # Collect price info
            price_range = []
            for s in sizes:
                pp = s.get("PricePerTier", "")
                su = s.get("PriceUnit", "") or price_unit
                try:
                    # For fixed/linear prices, single value
                    p = float(pp)
                    price_range.append(p)
                except (ValueError, TypeError):
                    # For tiered, take all tier prices
                    for part in str(pp).split(","):
                        try:
                            price_range.append(float(part.strip()))
                        except ValueError:
                            pass

            size_names = [s.get("Name", "?") for s in sizes if s.get("Name", "?") != "default"]

            summary = f"{fname} ({period}"
            if price_unit:
                summary += f", unit={price_unit}"
            if size_names:
                summary += f", sizes=[{', '.join(size_names[:5])}"
                if len(size_names) > 5:
                    summary += f"...+{len(size_names)-5}"
                summary += "]"
            if price_range:
                non_zero = [p for p in price_range if p > 0]
                if non_zero:
                    summary += f", CNY {min(non_zero):.2f}"
                    if len(non_zero) > 1:
                        summary += f"~{max(non_zero):.2f}"
            summary += ")"
            feature_summaries.append(summary)

            if fname.lower() != "default":
                all_meters.append(fname)

        type_summaries.append(f"{tname}: [{', '.join(feature_summaries)}]")

    ref["structure"] = type_summaries
    if all_meters:
        ref["meters_cn"] = all_meters

    return ref


def generate_config(slug: str, template: dict, mapping: dict, raw_svc: dict | None) -> dict:
    """Generate a draft service config from dimension template + raw legacy data."""
    suggested = template.get("suggested_config", {})
    pattern = suggested.get("pricing_pattern", "B")
    quantity_model = suggested.get("quantity_model", "per_meter")

    # Determine service_name from mapping
    if slug in mapping:
        service_name = mapping[slug]["service_name"]
        display_name_cn = mapping[slug].get("display_name_cn", "")
    else:
        service_name = template.get("display_name", slug)
        display_name_cn = template.get("display_name", "")

    config = {
        "service_name": service_name,
        "quantity_model": quantity_model,
    }

    # quantity_label
    if quantity_model == "instances_x_hours":
        config["quantity_label"] = "Instances"
    else:
        config["quantity_label"] = "Usage"

    # dimension_labels
    types = template.get("types", [])
    types_semantic = template.get("types_semantic", "")

    if suggested.get("dimension_labels"):
        config["dimension_labels"] = suggested["dimension_labels"]

    # hidden_dimensions
    if suggested.get("hidden_dimensions"):
        config["hidden_dimensions"] = suggested["hidden_dimensions"]

    # --- Pattern-specific generation ---

    if types_semantic == "tier" and len(types) > 1:
        # Generate sku_groups: Chinese tier → English API value
        sku_groups = {}
        for t in types:
            cn_name = t["name"]
            en_name = TIER_CN_TO_EN.get(cn_name, cn_name)
            sku_groups[en_name] = [en_name]
        config["sku_groups"] = sku_groups

    if quantity_model == "per_meter":
        # Collect meter names from named features
        meter_names = []
        for t in types:
            for f in t.get("features", []):
                fname = f.get("name", "")
                if fname.lower() != "default" and fname not in meter_names:
                    meter_names.append(fname)

        if meter_names:
            # meter_order: use Chinese names as starting point (needs manual API alignment)
            config["meter_order"] = meter_names
            # Note: meter_labels need to be filled after checking Global API meter names

    # defaults: use chinaeast2 as default for CN calculator
    config["defaults"] = {
        "selections": {
            "armRegionName": "chinaeast2",
        },
        "hours_per_month": 730,
    }

    # Add sku default for tier products
    if types_semantic == "tier" and len(types) > 1:
        first_tier_cn = types[0]["name"]
        first_tier_en = TIER_CN_TO_EN.get(first_tier_cn, first_tier_cn)
        config["defaults"]["selections"]["skuName"] = first_tier_en

    # --- Legacy reference for human review ---
    legacy_ref = build_legacy_reference(slug, raw_svc)
    legacy_ref["pricing_pattern"] = pattern
    legacy_ref["pricing_pattern_name"] = PATTERN_NAMES.get(pattern, "unknown")
    if display_name_cn:
        legacy_ref["display_name_cn"] = display_name_cn
    config["_legacy_reference"] = legacy_ref

    return config


def main():
    # Parse args
    batch = "1"
    single_slug = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--batch" and i + 1 < len(args):
            batch = args[i + 1]
            i += 2
        elif args[i] == "--slug" and i + 1 < len(args):
            single_slug = args[i + 1]
            i += 2
        else:
            i += 1

    if single_slug:
        slugs = [single_slug]
    elif batch == "2":
        slugs = BATCH_2
    elif batch == "all":
        slugs = BATCH_1 + BATCH_2
    else:
        slugs = BATCH_1

    mapping = load_mapping()
    existing = get_existing_configs()
    datamodel = load_datamodel()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped = 0

    print(f"Generating service configs for {len(slugs)} products (batch={batch})...\n")

    for slug in slugs:
        template_path = TEMPLATES_DIR / f"{slug}.json"
        if not template_path.exists():
            print(f"  SKIP (no dimension template): {slug}")
            skipped += 1
            continue

        template = json.loads(template_path.read_text("utf-8"))
        raw_svc = datamodel.get(slug)
        config = generate_config(slug, template, mapping, raw_svc)

        # Status indicator
        if config["service_name"] in existing:
            label = "has-config"
        else:
            label = "NEW"

        pattern = config.get("_legacy_reference", {}).get("pricing_pattern", "?")

        output_path = OUTPUT_DIR / f"{slug}.json"
        output_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", "utf-8")
        generated += 1

        print(f"  [{label}] Pattern {pattern}: {slug}")
        print(f"           → {config['service_name']} ({config['quantity_model']})")

    print(f"\nGenerated: {generated}, Skipped: {skipped}")
    print(f"Output: {OUTPUT_DIR}/")
    print()
    print("Next steps for each template:")
    print("  1. Verify service_name matches Azure Global API serviceName")
    print("  2. Use Admin UI API Preview Tab to check cascade/meters data")
    print("  3. Fill meter_labels with English meter names from API")
    print("  4. Adjust meter_order based on API meter names")
    print("  5. Remove _legacy_reference section before publishing")


if __name__ == "__main__":
    main()
