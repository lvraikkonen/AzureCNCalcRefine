"""Admin API — CRUD for service configurations and product catalog.

Authentication: Bearer token from ADMIN_TOKEN environment variable.
If ADMIN_TOKEN is not set, admin endpoints are open (development mode).

All endpoints are under /api/v1/admin/.
"""

import json
import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.config import ProductFamily, ServiceConfig, ServiceConfigHistory
from app.schemas.admin import (
    FamilyCreate,
    FamilyResponse,
    FamilyUpdate,
    ImportJsonFilesRequest,
    ImportResponse,
    ImportResult,
    ReorderRequest,
    ServiceConfigCreate,
    ServiceConfigHistoryItem,
    ServiceConfigListItem,
    ServiceConfigPublish,
    ServiceConfigResponse,
    ServiceConfigRevert,
    ServiceConfigUpdate,
    ServiceConfigValidate,
    ServiceEntryCreate,
    ServiceEntryResponse,
    ServiceEntryUpdate,
    ValidationResult,
)
from app.services import config_repo
from app.services.catalog_cache import invalidate_catalog_cache, load_catalog_to_cache
from app.services.config_validator import validate_config
from sqlalchemy import select, update

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config" / "service_configs"
_CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "product_catalog.json"


def _export_config_json(slug: str, config: dict) -> None:
    """Publish 后将 config 同步写入 JSON 文件（版本控制备份 + 无 DB 降级用）。"""
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        path = _CONFIG_DIR / f"{slug}.json"
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass  # JSON export is best-effort; don't fail the publish


def _export_catalog_json() -> None:
    """Catalog 变更后将当前缓存同步写入 product_catalog.json。"""
    from app.services.catalog_cache import get_cached_catalog
    catalog = get_cached_catalog()
    if catalog is None:
        return
    try:
        _CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass  # best-effort


# ---------------------------------------------------------------------------
# Authentication dependency
# ---------------------------------------------------------------------------


def _verify_token(authorization: Annotated[str | None, Header()] = None) -> None:
    """Verify Bearer token if ADMIN_TOKEN env var is set."""
    admin_token = os.environ.get("ADMIN_TOKEN")
    if not admin_token:
        return  # Open in development mode
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")
    token = authorization.removeprefix("Bearer ").strip()
    if token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")


AdminAuth = Annotated[None, Depends(_verify_token)]
DBSession = Annotated[AsyncSession, Depends(get_session)]


# ---------------------------------------------------------------------------
# Service Config CRUD
# ---------------------------------------------------------------------------


@router.get("/configs", response_model=list[ServiceConfigListItem])
async def list_configs(
    _: AdminAuth,
    session: DBSession,
    status: str | None = Query(None, description="Filter by status: draft, published, archived"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """List all service configurations."""
    return await config_repo.list_configs(session, status=status, offset=offset, limit=limit)


@router.get("/configs/{service_name}", response_model=ServiceConfigResponse)
async def get_config(service_name: str, _: AdminAuth, session: DBSession):
    """Get a single service configuration by service name."""
    obj = await config_repo.get_config(session, service_name)
    if not obj:
        raise HTTPException(status_code=404, detail=f"Config not found: {service_name}")
    return obj


@router.post("/configs", response_model=ServiceConfigResponse, status_code=201)
async def create_config(body: ServiceConfigCreate, _: AdminAuth, session: DBSession):
    """Create a new service configuration (status: draft)."""
    existing = await config_repo.get_config(session, body.service_name)
    if existing:
        raise HTTPException(
            status_code=409, detail=f"Config already exists: {body.service_name}"
        )
    errors, _ = validate_config(body.config)
    if errors:
        raise HTTPException(status_code=422, detail={"validation_errors": errors})

    slug = body.slug or body.service_name.lower().replace(" ", "_")
    return await config_repo.create_config(
        session, body.service_name, slug, body.config, body.changed_by
    )


@router.put("/configs/{service_name}", response_model=ServiceConfigResponse)
async def update_config(
    service_name: str, body: ServiceConfigUpdate, _: AdminAuth, session: DBSession
):
    """Update an existing config (saves history, reverts to draft)."""
    errors, _ = validate_config(body.config)
    if errors:
        raise HTTPException(status_code=422, detail={"validation_errors": errors})
    try:
        obj = await config_repo.update_config(
            session, service_name, body.config, body.changed_by, body.change_summary
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return obj


@router.delete("/configs/{service_name}", status_code=204)
async def archive_config(service_name: str, _: AdminAuth, session: DBSession):
    """Soft-delete a config (set status to archived)."""
    try:
        await config_repo.archive_config(session, service_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/configs/{service_name}/publish", response_model=ServiceConfigResponse)
async def publish_config(
    service_name: str, body: ServiceConfigPublish, _: AdminAuth, session: DBSession
):
    """Publish a draft config (makes it live for the Explore API)."""
    try:
        obj = await config_repo.publish_config(session, service_name, body.changed_by)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    config_repo.set_cached_config(service_name, obj.config)
    _export_config_json(obj.slug, obj.config)
    return obj


@router.post("/configs/{service_name}/revert/{version}", response_model=ServiceConfigResponse)
async def revert_config(
    service_name: str, version: int, body: ServiceConfigRevert, _: AdminAuth, session: DBSession
):
    """Revert a config to a specific historical version (creates a new version)."""
    try:
        obj = await config_repo.revert_config(session, service_name, version, body.changed_by)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return obj


@router.get("/configs/{service_name}/history", response_model=list[ServiceConfigHistoryItem])
async def get_config_history(service_name: str, _: AdminAuth, session: DBSession):
    """Get version history for a service configuration."""
    return await config_repo.get_config_history(session, service_name)


@router.post("/configs/{service_name}/validate", response_model=ValidationResult)
async def validate_config_endpoint(
    service_name: str, body: ServiceConfigValidate, _: AdminAuth
):
    """Validate a config without saving it."""
    errors, warnings = validate_config(body.config)
    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


# ---------------------------------------------------------------------------
# Product Catalog CRUD
# ---------------------------------------------------------------------------


@router.get("/catalog/families", response_model=list[FamilyResponse])
async def list_families(_: AdminAuth, session: DBSession):
    """List all product families with their services."""
    return await config_repo.get_catalog(session)


@router.post("/catalog/families", response_model=FamilyResponse, status_code=201)
async def create_family(body: FamilyCreate, _: AdminAuth, session: DBSession):
    """Create a new product family."""
    existing = await config_repo.get_family(session, body.key)
    if existing:
        raise HTTPException(status_code=409, detail=f"Family already exists: {body.key}")
    family = await config_repo.create_family(session, body.key, body.label, body.order)
    await _refresh_catalog_cache(session)
    return family


@router.put("/catalog/families/{key}", response_model=FamilyResponse)
async def update_family(key: str, body: FamilyUpdate, _: AdminAuth, session: DBSession):
    """Update a product family."""
    try:
        family = await config_repo.update_family(session, key, body.label, body.order)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await _refresh_catalog_cache(session)
    return family


@router.delete("/catalog/families/{key}", status_code=204)
async def delete_family(key: str, _: AdminAuth, session: DBSession):
    """Delete an empty product family."""
    try:
        await config_repo.delete_family(session, key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await _refresh_catalog_cache(session)


@router.post("/catalog/services", response_model=ServiceEntryResponse, status_code=201)
async def create_service_entry(body: ServiceEntryCreate, _: AdminAuth, session: DBSession):
    """Add a service to the product catalog."""
    try:
        svc = await config_repo.create_service_entry(
            session,
            body.family_key,
            body.service_name,
            body.description,
            body.icon,
            body.popular,
            body.display_name_cn,
            body.region_constraints,
            body.order,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await _refresh_catalog_cache(session)
    return svc


@router.put("/catalog/services/{service_name}", response_model=ServiceEntryResponse)
async def update_service_entry(
    service_name: str, body: ServiceEntryUpdate, _: AdminAuth, session: DBSession
):
    """Update a service catalog entry."""
    update_kwargs = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        svc = await config_repo.update_service_entry(session, service_name, **update_kwargs)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await _refresh_catalog_cache(session)
    return svc


@router.delete("/catalog/services/{service_name}", status_code=204)
async def delete_service_entry(service_name: str, _: AdminAuth, session: DBSession):
    """Remove a service from the product catalog."""
    try:
        await config_repo.delete_service_entry(session, service_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await _refresh_catalog_cache(session)


@router.post("/catalog/reorder", status_code=204)
async def reorder_catalog(body: ReorderRequest, _: AdminAuth, session: DBSession):
    """Batch reorder families and/or services."""
    if body.families:
        for item in body.families:
            await session.execute(
                update(ProductFamily)
                .where(ProductFamily.key == item.key)
                .values(order=item.order)
            )
    if body.services:
        from app.models.config import ProductService
        for item in body.services:
            await session.execute(
                update(ProductService)
                .where(ProductService.service_name == item.key)
                .values(order=item.order)
            )
    await session.commit()
    await _refresh_catalog_cache(session)


# ---------------------------------------------------------------------------
# Bulk import
# ---------------------------------------------------------------------------


@router.post("/import/json-files", response_model=ImportResponse)
async def import_from_json_files(
    body: ImportJsonFilesRequest, _: AdminAuth, session: DBSession
):
    """Import all service config JSON files from app/config/service_configs/ into DB."""
    results: list[ImportResult] = []
    counts = {"created": 0, "updated": 0, "skipped": 0, "error": 0}

    config_files = sorted(_CONFIG_DIR.glob("*.json"))
    for config_path in config_files:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            service_name = config.get("service_name", "")
            if not service_name:
                service_name = config_path.stem.replace("_", " ").title()
            slug = config_path.stem

            existing = await config_repo.get_config(session, service_name)
            if existing:
                if not body.overwrite:
                    results.append(ImportResult(action="skipped", service_name=service_name))
                    counts["skipped"] += 1
                    continue
                await config_repo.update_config(
                    session, service_name, config, "import_api", "Re-imported from JSON file"
                )
                results.append(ImportResult(action="updated", service_name=service_name))
                counts["updated"] += 1
            else:
                await config_repo.create_config(session, service_name, slug, config, "import_api")
                results.append(ImportResult(action="created", service_name=service_name))
                counts["created"] += 1

        except Exception as exc:
            results.append(
                ImportResult(action="error", service_name=config_path.stem, detail=str(exc))
            )
            counts["error"] += 1

    return ImportResponse(
        results=results,
        total=len(results),
        **counts,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _refresh_catalog_cache(session: AsyncSession) -> None:
    """Reload the catalog from DB into the in-memory cache, then export to JSON."""
    try:
        await load_catalog_to_cache(session)
        _export_catalog_json()
    except Exception:
        invalidate_catalog_cache()  # Force next request to use JSON fallback
