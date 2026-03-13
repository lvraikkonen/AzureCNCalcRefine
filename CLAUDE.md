# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Azure.cn Pricing Calculator — a backend-focused reimplementation of the Azure international Pricing Calculator for the Azure China (azure.cn) site. Delivers pricing APIs and a minimal demo frontend.

**Tech stack**: Python + FastAPI + PostgreSQL + SQLAlchemy + Alembic
**Data source**: Azure.cn retail price CSV (~47k rows, CNY currency)
**Language context**: Implementation plan and comments are in Chinese; code and APIs use English identifiers.

## Common Commands

```bash
# Package manager: uv (https://docs.astral.sh/uv/)

# Install dependencies (defined in pyproject.toml)
uv sync

# Database migrations
uv run alembic upgrade head

# Import pricing data from CSV into PostgreSQL
uv run python scripts/import_data.py

# Run the API server
uv run uvicorn app.main:app --reload

# Run tests
uv run pytest
uv run pytest tests/test_pricing_api.py          # single test file
uv run pytest tests/test_pricing_api.py::test_x  # single test function

# Add a dependency
uv add <package>
uv add --dev <package>          # dev dependency
```

## Architecture

### Data Flow
```
Azure.cn CSV API → downloader.py → parser.py (clean/validate) → importer.py (staging table → TRUNCATE+INSERT → REFRESH materialized view)
```

### Database
- **`retail_prices`** — core table, direct mapping of CSV columns (meter_id, sku_id, product_name, sku_name, service_name, service_family, arm_region_name, type, term, tier_min_units, retail_price, unit_price, etc.)
- **`product_catalog`** — materialized view aggregated from retail_prices for product listing (refreshed on data import)
- Requires `pg_trgm` extension for fuzzy search indexes

### API Layers (app/)
- **`api/`** — FastAPI route handlers (products, configuration, pricing, export)
- **`services/`** — business logic (product_service, config_service, pricing_service, export_service)
- **`schemas/`** — Pydantic request/response models
- **`models/`** — SQLAlchemy ORM models
- **`data_pipeline/`** — CSV download, parse, and import logic

### Key API Endpoints
| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/products/categories` | Service family → service name tree |
| `GET /api/v1/products/search` | Product search with fuzzy matching |
| `POST /api/v1/products/{service_name}/configurations` | Cascading filter — returns available options per dimension given current selections |
| `POST /api/v1/products/{service_name}/meters` | Meter list with tiered pricing for a configured product |
| `POST /api/v1/pricing/calculate` | Multi-item price calculation with tiered pricing support |
| `POST /api/v1/export/excel` | Excel export of estimate |

### Core Algorithm: Cascading Filter
The cascading filter is the central interaction. Dimension order: `arm_region_name → product_name → sku_name → type → term`. For each dimension, query available options by applying all *other* selected dimensions as filters. The `term` dimension is only visible when `type` is Reservation or SavingsPlanConsumption. DevTestConsumption is excluded by default.

### Tiered Pricing
Some products (e.g., Storage Hot LRS) use tiered pricing via `tier_min_units`. Multiple price rows exist for the same meter at different tier thresholds. The pricing engine must apply the correct tier rates based on usage quantity.

### Frontend
Minimal single-page demo (`frontend/`) using vanilla HTML/JS/CSS, served as FastAPI static files. Not a production frontend.
