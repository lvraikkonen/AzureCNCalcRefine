"""
Generate draft service_config JSON files from ACN dimension templates.

Usage: python scripts/generate_service_configs.py

Input:  data/acn_dimension_templates/*.json
Output: data/generated_service_configs/*.json (for human review, NOT production)

These drafts follow the project's service_config format and should be manually
reviewed and adjusted before copying to app/config/service_configs/.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "data" / "acn_dimension_templates"
OUTPUT_DIR = ROOT / "data" / "generated_service_configs"
EXISTING_DIR = ROOT / "app" / "config" / "service_configs"
NAMES_PATH = ROOT / "data" / "acn_product_names.json"
MAPPING_PATH = ROOT / "data" / "slug_to_service_name.json"

# Slugs to generate configs for (from acn-datamodel-todo.md)
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

ALL_SLUGS = BATCH_1 + BATCH_2


def load_mapping() -> dict[str, dict]:
    """Load slug -> service_name mapping."""
    if not MAPPING_PATH.exists():
        return {}
    data = json.loads(MAPPING_PATH.read_text("utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def get_existing_configs() -> set[str]:
    """Return set of service names that already have configs."""
    existing = set()
    for p in EXISTING_DIR.glob("*.json"):
        try:
            cfg = json.loads(p.read_text("utf-8"))
            existing.add(cfg.get("service_name", ""))
        except (json.JSONDecodeError, KeyError):
            pass
    return existing


def generate_config(slug: str, template: dict, mapping: dict) -> dict | None:
    """Generate a draft service config from a dimension template."""
    suggested = template.get("suggested_config", {})

    # Determine service_name
    if slug in mapping:
        service_name = mapping[slug]["service_name"]
    else:
        # Use display_name as service_name guess
        service_name = template.get("display_name", slug)

    config = {
        "service_name": service_name,
        "_acn_slug": slug,
        "_acn_display_name": template.get("display_name", ""),
    }

    # quantity_model
    config["quantity_model"] = suggested.get("quantity_model", "per_meter")

    # quantity_label
    if config["quantity_model"] == "instances_x_hours":
        config["quantity_label"] = "Instances"
    else:
        config["quantity_label"] = "Usage"

    # dimension_labels
    if suggested.get("dimension_labels"):
        config["dimension_labels"] = suggested["dimension_labels"]

    # hidden_dimensions
    if suggested.get("hidden_dimensions"):
        config["hidden_dimensions"] = suggested["hidden_dimensions"]

    # Analyze types for sku_groups
    types = template.get("types", [])
    types_semantic = template.get("types_semantic", "")

    if types_semantic == "tier" and len(types) > 1:
        # Generate sku_groups mapping Chinese tier names to expected API skuNames
        sku_groups = {}
        for t in types:
            name = t["name"]
            # Map Chinese tier names to likely API skuNames
            tier_map = {
                "免费": "Free",
                "基本": "Basic",
                "标准": "Standard",
                "高级": "Premium",
                "共享": "Shared",
                "专用": "Dedicated",
                "隔离": "Isolated",
                "免费版": "Free",
                "标准版": "Standard",
                "高级版": "Premium",
            }
            api_name = tier_map.get(name, name)
            sku_groups[name] = [api_name]
        config["sku_groups"] = sku_groups

    # meter_labels and meter_order from named features
    if config["quantity_model"] == "per_meter":
        meter_names = []
        for t in types:
            for f in t.get("features", []):
                fname = f.get("name", "")
                if fname.lower() != "default" and fname not in meter_names:
                    meter_names.append(fname)
        if meter_names:
            config["meter_order"] = meter_names
            # meter_labels: use feature names as-is (they're already descriptive)

    # defaults
    config["defaults"] = {
        "selections": {
            "armRegionName": "eastus",
        },
        "hours_per_month": 730,
    }

    return config


def main():
    mapping = load_mapping()
    existing = get_existing_configs()
    acn_names = json.loads(NAMES_PATH.read_text("utf-8")) if NAMES_PATH.exists() else {}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped_existing = 0
    skipped_missing = 0

    for slug in ALL_SLUGS:
        template_path = TEMPLATES_DIR / f"{slug}.json"
        if not template_path.exists():
            print(f"  SKIP (no template): {slug}")
            skipped_missing += 1
            continue

        template = json.loads(template_path.read_text("utf-8"))
        config = generate_config(slug, template, mapping)
        if not config:
            continue

        # Check if already has a production config
        if config["service_name"] in existing:
            label = "(existing)"
        else:
            label = "(NEW)"

        output_path = OUTPUT_DIR / f"{slug}.json"
        output_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", "utf-8")
        generated += 1
        print(f"  Generated {label}: {slug} -> {config['service_name']} ({config['quantity_model']})")

    print(f"\nSummary: {generated} configs generated, {skipped_missing} missing templates")
    print(f"Output: {OUTPUT_DIR}/")
    print("\nNext steps:")
    print("  1. Review each generated config in data/generated_service_configs/")
    print("  2. Verify api_service_name against actual Azure API")
    print("  3. Copy approved configs to app/config/service_configs/")
    print("  4. Test via POST /explore/cascade + POST /explore/meters")


if __name__ == "__main__":
    main()
