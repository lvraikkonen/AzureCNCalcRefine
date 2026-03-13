#!/usr/bin/env python3
"""Azure Global Retail Prices API 交互式探索工具。

用于调研 Azure 定价数据结构、验证子维度假设、对比 Global vs CN 数据。

依赖: httpx, rich
用法:
    python scripts/explore_global_api.py service "Virtual Machines" --region eastus
    python scripts/explore_global_api.py cascade "Storage" --region eastus --product "Blob Storage"
    python scripts/explore_global_api.py subdimensions "Storage" --field sku_name
    python scripts/explore_global_api.py meters "Storage" --product "Blob Storage" --sku "Hot LRS" --region eastus
    python scripts/explore_global_api.py compare "Virtual Machines" --product "Virtual Machines Dv3 Series"
    python scripts/explore_global_api.py productparse "Virtual Machines" --region eastus
"""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

GLOBAL_API_URL = "https://prices.azure.com/api/retail/prices"
CN_CSV_PATH = Path(__file__).parent.parent / "sample-data" / "AzureRetailPrices.csv"

console = Console()


def get_effective_term(item: dict) -> str:
    """Return effective term: reservationTerm for Reservation, else term."""
    return item.get("reservationTerm") or item.get("term") or ""


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def fetch_global_prices(filters: dict, max_pages: int = 10) -> list[dict]:
    """Query Azure Global Retail Prices API with OData filters.

    Args:
        filters: key-value pairs for $filter (e.g. {"serviceName": "Storage"}).
        max_pages: safety cap on pagination.

    Returns:
        List of price item dicts.
    """
    parts = [f"{k} eq '{v}'" for k, v in filters.items()]
    odata_filter = " and ".join(parts)

    items: list[dict] = []
    url = GLOBAL_API_URL
    params = {"$filter": odata_filter}

    with httpx.Client(timeout=30) as client:
        for _ in range(max_pages):
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get("Items", []))
            next_link = data.get("NextPageLink")
            if not next_link:
                break
            url = next_link
            params = {}

    return items


def load_cn_csv() -> list[dict]:
    """Load Chinese region CSV data."""
    if not CN_CSV_PATH.exists():
        console.print(f"[yellow]CN CSV not found at {CN_CSV_PATH}[/yellow]")
        return []
    with open(CN_CSV_PATH, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_service(args: argparse.Namespace) -> None:
    """按服务查询 + 维度分布汇总。"""
    filters: dict[str, str] = {"serviceName": args.service}
    if args.region:
        filters["armRegionName"] = args.region

    console.print(f"[bold]Querying Global API: {filters}[/bold]")
    items = fetch_global_prices(filters)
    console.print(f"Total rows: {len(items)}\n")

    if not items:
        return

    dimensions = ["productName", "skuName", "type", "term", "unitOfMeasure"]
    for dim in dimensions:
        if dim == "term":
            counter = Counter(
                get_effective_term(item) or "(empty)" for item in items
            )
        else:
            counter = Counter(item.get(dim, "(empty)") for item in items)
        table = Table(title=f"{dim} ({len(counter)} distinct)")
        table.add_column("Value", style="cyan")
        table.add_column("Count", justify="right")
        for val, cnt in counter.most_common(30):
            table.add_row(str(val), str(cnt))
        if len(counter) > 30:
            table.add_row("...", f"({len(counter) - 30} more)")
        console.print(table)
        console.print()


def cmd_cascade(args: argparse.Namespace) -> None:
    """模拟级联筛选。"""
    filters: dict[str, str] = {"serviceName": args.service}
    if args.region:
        filters["armRegionName"] = args.region
    if args.product:
        filters["productName"] = args.product
    if args.sku:
        filters["skuName"] = args.sku

    console.print(f"[bold]Cascade query: {filters}[/bold]")
    items = fetch_global_prices(filters)
    console.print(f"Total rows: {len(items)}\n")

    if not items:
        return

    # Filter to primary meter region and exclude DevTest
    items = [
        i for i in items
        if i.get("isPrimaryMeterRegion", True)
        and i.get("type") != "DevTestConsumption"
    ]

    cascade_dims = [
        ("armRegionName", "Region"),
        ("productName", "Product"),
        ("skuName", "SKU"),
        ("type", "Pricing Type"),
        ("term", "Term"),
    ]

    for field, label in cascade_dims:
        if field == "term":
            values = sorted({get_effective_term(item) for item in items if get_effective_term(item)})
        else:
            values = sorted({item.get(field, "") for item in items if item.get(field)})
        table = Table(title=f"{label} ({field}) — {len(values)} options")
        table.add_column("Value", style="cyan")
        for v in values[:50]:
            table.add_row(v)
        if len(values) > 50:
            table.add_row(f"... ({len(values) - 50} more)")
        console.print(table)
        console.print()


def cmd_subdimensions(args: argparse.Namespace) -> None:
    """分析 productName/skuName 的子维度模式。"""
    field = args.field
    if field not in ("productName", "skuName", "product_name", "sku_name"):
        console.print("[red]--field must be productName or skuName[/red]")
        return

    # Normalize to API field name
    api_field = field.replace("_", "")
    api_field = {"productname": "productName", "skuname": "skuName"}.get(
        api_field.lower(), api_field
    )

    filters: dict[str, str] = {"serviceName": args.service}
    if args.region:
        filters["armRegionName"] = args.region

    console.print(f"[bold]Sub-dimension analysis: {args.service} / {api_field}[/bold]")
    items = fetch_global_prices(filters)

    values = sorted({item.get(api_field, "") for item in items if item.get(api_field)})
    console.print(f"Distinct {api_field} values: {len(values)}\n")

    # Display all values
    table = Table(title=f"All {api_field} values")
    table.add_column("#", justify="right")
    table.add_column("Value", style="cyan")
    table.add_column("Word count", justify="right")
    for i, v in enumerate(values, 1):
        table.add_row(str(i), v, str(len(v.split())))
    console.print(table)
    console.print()

    # Analyze split patterns
    if api_field == "skuName":
        console.print("[bold]Split analysis (first word vs rest):[/bold]")
        first_words: set[str] = set()
        rest_words: set[str] = set()
        for v in values:
            parts = v.split(" ", 1)
            first_words.add(parts[0])
            if len(parts) > 1:
                rest_words.add(parts[1])

        console.print(f"  First word candidates: {sorted(first_words)}")
        console.print(f"  Rest candidates:       {sorted(rest_words)}")
    else:
        # productName: show common prefix/suffix patterns
        console.print("[bold]Common prefixes (first 40 chars):[/bold]")
        prefix_counter = Counter(v[:40] for v in values)
        for prefix, cnt in prefix_counter.most_common(10):
            console.print(f"  [{cnt:3d}] {prefix}...")


def cmd_meters(args: argparse.Namespace) -> None:
    """查看具体配置的 meter/tier 结构。"""
    filters: dict[str, str] = {"serviceName": args.service}
    if args.region:
        filters["armRegionName"] = args.region
    if args.product:
        filters["productName"] = args.product
    if args.sku:
        filters["skuName"] = args.sku

    console.print(f"[bold]Meters query: {filters}[/bold]")
    items = fetch_global_prices(filters)

    # Group by (meterName, type, term) and collect tiers
    meter_groups: dict[tuple, list[dict]] = defaultdict(list)
    for item in items:
        key = (
            item.get("meterName", ""),
            item.get("type", ""),
            get_effective_term(item),
        )
        meter_groups[key].append(item)

    table = Table(title=f"Meters ({len(meter_groups)} groups)")
    table.add_column("Product", style="dim")
    table.add_column("SKU", style="dim")
    table.add_column("Meter", style="cyan")
    table.add_column("Type")
    table.add_column("Term")
    table.add_column("Unit")
    table.add_column("Tiers", justify="right")
    table.add_column("Prices")

    for (meter, typ, term), rows in sorted(meter_groups.items()):
        tiers = sorted(rows, key=lambda r: float(r.get("tierMinimumUnits", 0)))
        is_reservation = typ == "Reservation"
        tier_str = " | ".join(
            f"{r.get('tierMinimumUnits', 0)}→{r.get('unitPrice', '?')}"
            + (" (total)" if is_reservation else "")
            for r in tiers
        )
        table.add_row(
            rows[0].get("productName", ""),
            rows[0].get("skuName", ""),
            meter,
            typ,
            term or "-",
            rows[0].get("unitOfMeasure", ""),
            str(len(tiers)),
            tier_str,
        )

    console.print(table)

    # --raw N: dump raw JSON items
    if getattr(args, "raw", None):
        console.print(f"\n[bold]Raw JSON dump (first {args.raw} items):[/bold]")
        for item in items[: args.raw]:
            console.print(json.dumps(item, indent=2, ensure_ascii=False))


def cmd_compare(args: argparse.Namespace) -> None:
    """对比 Global vs CN 数据。"""
    # Global data
    filters: dict[str, str] = {"serviceName": args.service}
    if args.product:
        filters["productName"] = args.product

    console.print(f"[bold]Fetching Global data: {filters}[/bold]")
    global_items = fetch_global_prices(filters)

    # CN data
    cn_rows = load_cn_csv()
    if not cn_rows:
        console.print("[yellow]Skipping CN comparison (no CSV)[/yellow]")
        return

    cn_items = [r for r in cn_rows if r.get("serviceName") == args.service]
    if args.product:
        cn_items = [r for r in cn_items if r.get("productName") == args.product]

    console.print(f"Global rows: {len(global_items)}, CN rows: {len(cn_items)}\n")

    # Compare dimensions
    dims = ["armRegionName", "productName", "skuName", "type", "term"]
    tree = Tree(f"[bold]{args.service}[/bold] — dimension comparison")

    for dim in dims:
        if dim == "term":
            global_vals = {get_effective_term(item) for item in global_items if get_effective_term(item)}
        else:
            global_vals = {item.get(dim, "") for item in global_items if item.get(dim)}
        cn_vals = {item.get(dim, "") for item in cn_items if item.get(dim)}

        branch = tree.add(f"[bold]{dim}[/bold]")
        both = sorted(global_vals & cn_vals)
        global_only = sorted(global_vals - cn_vals)
        cn_only = sorted(cn_vals - global_vals)

        if both:
            b = branch.add(f"[green]Both ({len(both)})[/green]")
            for v in both[:15]:
                b.add(v)
            if len(both) > 15:
                b.add(f"... ({len(both) - 15} more)")
        if global_only:
            b = branch.add(f"[blue]Global only ({len(global_only)})[/blue]")
            for v in global_only[:15]:
                b.add(v)
            if len(global_only) > 15:
                b.add(f"... ({len(global_only) - 15} more)")
        if cn_only:
            b = branch.add(f"[red]CN only ({len(cn_only)})[/red]")
            for v in cn_only[:15]:
                b.add(v)
            if len(cn_only) > 15:
                b.add(f"... ({len(cn_only) - 15} more)")

    console.print(tree)


def cmd_productparse(args: argparse.Namespace) -> None:
    """使用 vm_parser 解析 productName 子维度。"""
    # Lazy import — vm_parser only depends on re + dataclasses, no DB deps
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from app.services.sub_dimensions.vm_parser import parse_vm_product_name

    filters: dict[str, str] = {"serviceName": args.service}
    if args.region:
        filters["armRegionName"] = args.region
    if args.product:
        filters["productName"] = args.product

    console.print(f"[bold]Fetching data for productparse: {filters}[/bold]")
    items = fetch_global_prices(filters)
    console.print(f"Total rows: {len(items)}\n")

    if not items:
        return

    # Unique productNames
    product_names = sorted({item.get("productName", "") for item in items if item.get("productName")})
    console.print(f"Unique productName values: {len(product_names)}\n")

    # Parse each and build table
    table = Table(title=f"Parsed Sub-dimensions ({len(product_names)} products)")
    table.add_column("#", justify="right")
    table.add_column("productName", style="cyan")
    table.add_column("OS")
    table.add_column("Deployment")
    table.add_column("Series")
    table.add_column("Category")
    table.add_column("Tier")
    table.add_column("Memory")
    table.add_column("Special")

    unparsed = []
    os_counter: Counter[str] = Counter()
    deploy_counter: Counter[str] = Counter()
    category_counter: Counter[str | None] = Counter()

    for i, pn in enumerate(product_names, 1):
        parsed = parse_vm_product_name(pn)
        os_counter[parsed.os] += 1
        deploy_counter[parsed.deployment] += 1
        category_counter[parsed.category] += 1

        if parsed.series is None and parsed.special is None:
            unparsed.append(pn)

        table.add_row(
            str(i),
            pn,
            parsed.os,
            parsed.deployment,
            parsed.series or "-",
            parsed.category or "-",
            parsed.tier or "-",
            parsed.memory_profile or "-",
            parsed.special or "-",
        )

    console.print(table)

    # Summary stats
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  OS distribution:         {dict(os_counter.most_common())}")
    console.print(f"  Deployment distribution: {dict(deploy_counter.most_common())}")
    console.print(f"  Category distribution:   {dict(category_counter.most_common())}")

    if unparsed:
        console.print(f"\n[yellow]Warning: {len(unparsed)} product(s) with no series or special flag:[/yellow]")
        for pn in unparsed:
            console.print(f"  - {pn}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Azure Global Retail Prices API Explorer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # service
    p = sub.add_parser("service", help="按服务查询 + 维度分布汇总")
    p.add_argument("service", help="serviceName (e.g. 'Virtual Machines')")
    p.add_argument("--region", help="armRegionName filter")

    # cascade
    p = sub.add_parser("cascade", help="模拟级联筛选")
    p.add_argument("service", help="serviceName")
    p.add_argument("--region", help="armRegionName")
    p.add_argument("--product", help="productName")
    p.add_argument("--sku", help="skuName")

    # subdimensions
    p = sub.add_parser("subdimensions", help="子维度模式分析")
    p.add_argument("service", help="serviceName")
    p.add_argument("--field", default="skuName", help="productName or skuName")
    p.add_argument("--region", help="armRegionName filter")

    # meters
    p = sub.add_parser("meters", help="Meter/Tier 结构查看")
    p.add_argument("service", help="serviceName")
    p.add_argument("--region", help="armRegionName")
    p.add_argument("--product", help="productName")
    p.add_argument("--sku", help="skuName")
    p.add_argument("--raw", type=int, metavar="N", help="Dump N raw JSON items at end")

    # compare
    p = sub.add_parser("compare", help="Global vs CN 数据对比")
    p.add_argument("service", help="serviceName")
    p.add_argument("--product", help="productName")

    # productparse
    p = sub.add_parser("productparse", help="使用 vm_parser 解析 productName 子维度")
    p.add_argument("service", help="serviceName (typically 'Virtual Machines')")
    p.add_argument("--region", help="armRegionName filter")
    p.add_argument("--product", help="productName filter")

    args = parser.parse_args()

    commands = {
        "service": cmd_service,
        "cascade": cmd_cascade,
        "subdimensions": cmd_subdimensions,
        "meters": cmd_meters,
        "compare": cmd_compare,
        "productparse": cmd_productparse,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
