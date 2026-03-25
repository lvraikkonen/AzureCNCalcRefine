# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project is an Azure Pricing Calculator. Primary languages: Python (backend/scripts), JavaScript (frontend), with JSON config files. Always validate implementation against actual Azure API data and production UI behavior, not assumptions.

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

**Explore API** (used by frontend demo — proxies Azure Global Retail Price API):
| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/explore/service-config/{service_name}` | Default selections/config for a service |
| `POST /api/v1/explore/cascade` | Cascading filter with sub-dimension support |
| `POST /api/v1/explore/meters` | All meter/tier pricing for a config (all type/term combos) |
| `POST /api/v1/explore/calculator` | Server-side price calculation (legacy, replaced by frontend local calc) |

**Products API** (catalog/search):
| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/products/catalog` | Full product catalog (families + services) |
| `GET /api/v1/products/search` | Product search by keyword |

**Production API** (backed by local PostgreSQL — not yet connected to frontend):
| Endpoint | Purpose |
|----------|---------|
| `POST /api/v1/products/{service_name}/configurations` | Cascading filter |
| `POST /api/v1/products/{service_name}/meters` | Meter list with tiered pricing |
| `POST /api/v1/pricing/calculate` | Multi-item price calculation |
| `POST /api/v1/export/excel` | Excel export of estimate |

### Core Algorithm: Cascading Filter
The cascading filter is the central interaction. Dimension order: `arm_region_name → product_name → sku_name → type → term`. For each dimension, query available options by applying all *other* selected dimensions as filters. The `term` dimension is only visible when `type` is Reservation or SavingsPlanConsumption. DevTestConsumption is excluded by default.

### Tiered Pricing
Some products (e.g., Storage Hot LRS) use tiered pricing via `tier_min_units`. Multiple price rows exist for the same meter at different tier thresholds. The pricing engine must apply the correct tier rates based on usage quantity.

### Frontend
Single-page demo (`frontend/`) using vanilla HTML/JS/CSS, served as FastAPI static files. Not a production frontend.

**Two-phase calculation model** (implemented in Task 1-6):
- Phase 1: Dimension changes → `POST /explore/cascade` → auto-select → `POST /explore/meters` (fetches all type/term pricing, cached in `item.metersCache`)
- Phase 2: Savings/quantity/duration changes → `pricing.js` local calculation (no API calls)

**Key frontend modules** (`frontend/js/`):
| Module | Role |
|--------|------|
| `pricing.js` | Pure-function pricing engine: `calculateTieredCost()`, `calculateLocalPrice()`, `getAvailableSavingsOptions()` |
| `api.js` | API client: `fetchCascade()`, `fetchMeters()`, `fetchServiceConfig()`, `fetchPreload()` |
| `state.js` | State management + event bus. Item fields: `metersCache`, `metersCacheKey`, `upfrontCost`, `hoursUnit` |
| `components/estimate-card.js` | Estimate card component: cascading dropdowns, savings radio buttons, duration unit switcher, meter breakdown, price summary |
| `components/nav-area.js` | Navigation: product catalog sidebar, search, "Add to estimate" |
| `components/summary-bar.js` | Sticky bottom bar with total cost |

## Azure API Guidelines

When working with Azure API data, use the actual API responses rather than guessing field names, unit types, or dimension structures. Meter quantities may use different units (e.g., freeOffset vs meterQuantities) - always verify unit alignment.
