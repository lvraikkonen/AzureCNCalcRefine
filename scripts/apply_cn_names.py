"""
Apply Chinese names and descriptions from ACN legacy data to product_catalog.json.

Usage: python scripts/apply_cn_names.py [--dry-run]

Input:
  data/slug_to_service_name.json   - manual slug -> service_name mapping
  data/acn_product_names.json      - extracted Chinese names + region constraints
  app/config/product_catalog.json  - current catalog

Output:
  Updates app/config/product_catalog.json in-place (unless --dry-run)
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "app" / "config" / "product_catalog.json"
MAPPING_PATH = ROOT / "data" / "slug_to_service_name.json"
NAMES_PATH = ROOT / "data" / "acn_product_names.json"

DRY_RUN = "--dry-run" in sys.argv


def main():
    mapping = json.loads(MAPPING_PATH.read_text("utf-8"))
    acn_names = json.loads(NAMES_PATH.read_text("utf-8"))
    catalog = json.loads(CATALOG_PATH.read_text("utf-8"))

    # Build service_name -> best mapping entry
    # (multiple slugs may map to the same service_name; first one wins)
    sn_to_info = {}
    for slug, info in mapping.items():
        if slug.startswith("_"):
            continue
        sn = info["service_name"]
        if sn not in sn_to_info:
            sn_to_info[sn] = {
                "display_name_cn": info.get("display_name_cn"),
                "description_cn": info.get("description_cn"),
                "slug": slug,
            }
            # Also pick up region constraints from acn_names if available
            if slug in acn_names and acn_names[slug].get("region_constraints"):
                sn_to_info[sn]["region_constraints"] = acn_names[slug]["region_constraints"]

    updated = 0
    not_mapped = []

    for family in catalog["families"]:
        for svc in family["services"]:
            sn = svc["service_name"]
            if sn not in sn_to_info:
                not_mapped.append(sn)
                continue

            info = sn_to_info[sn]
            changed = False

            # Apply Chinese display name
            if info.get("display_name_cn") and not svc.get("display_name_cn"):
                svc["display_name_cn"] = info["display_name_cn"]
                changed = True

            # Apply Chinese description (always replace — this is for azure.cn)
            old_desc = svc.get("description", "")
            if info.get("description_cn"):
                svc["description"] = info["description_cn"]
                if old_desc != info["description_cn"]:
                    changed = True

            # Apply region constraints
            if info.get("region_constraints") and not svc.get("region_constraints"):
                svc["region_constraints"] = info["region_constraints"]
                changed = True

            if changed:
                updated += 1
                print(f"  Updated: {sn}")
                if info.get("display_name_cn"):
                    print(f"    display_name_cn: {info['display_name_cn']}")
                if info.get("description_cn") and old_desc != info["description_cn"]:
                    print(f"    description: {old_desc!r} -> {info['description_cn']}")
                if info.get("region_constraints"):
                    print(f"    region_constraints: {info['region_constraints']}")

    if not_mapped:
        print(f"\nNot mapped ({len(not_mapped)} services):")
        for sn in not_mapped:
            print(f"  - {sn}")

    print(f"\nSummary: {updated} services updated, {len(not_mapped)} not mapped")

    if DRY_RUN:
        print("\n[DRY RUN] No files written.")
    else:
        CATALOG_PATH.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", "utf-8"
        )
        print(f"\nWritten: {CATALOG_PATH}")


if __name__ == "__main__":
    main()
