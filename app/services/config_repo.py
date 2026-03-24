"""Config repository — data access layer for service configurations and product catalog.

All database operations for service_configs, service_config_history,
product_families, and product_services tables.
"""

import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.config import (
    ProductFamily,
    ProductService,
    ServiceConfig,
    ServiceConfigHistory,
)

# ---------------------------------------------------------------------------
# In-memory cache for published service configs (TTL = 60 seconds)
# ---------------------------------------------------------------------------

_config_cache: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 60.0


def _cache_key(service_name: str) -> str:
    return service_name.lower()


def get_cached_config(service_name: str) -> dict | None:
    key = _cache_key(service_name)
    entry = _config_cache.get(key)
    if entry and (time.monotonic() - entry[1]) < _CACHE_TTL:
        return entry[0]
    return None


def set_cached_config(service_name: str, config: dict) -> None:
    _config_cache[_cache_key(service_name)] = (config, time.monotonic())


def invalidate_cache(service_name: str) -> None:
    _config_cache.pop(_cache_key(service_name), None)


def invalidate_all_cache() -> None:
    _config_cache.clear()


async def load_all_published_to_cache(session: AsyncSession) -> int:
    """Pre-load all published service configs into the in-memory cache at startup.

    Returns the number of configs loaded.
    """
    result = await session.execute(
        select(ServiceConfig.service_name, ServiceConfig.config).where(
            ServiceConfig.status == "published"
        )
    )
    count = 0
    for service_name, config in result.all():
        set_cached_config(service_name, config)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Service Config CRUD
# ---------------------------------------------------------------------------


async def get_published_config(session: AsyncSession, service_name: str) -> dict | None:
    """Return the JSONB config for a published service, or None.

    Results are cached for CACHE_TTL seconds to avoid per-request DB hits.
    """
    cached = get_cached_config(service_name)
    if cached is not None:
        return cached

    result = await session.execute(
        select(ServiceConfig.config).where(
            ServiceConfig.service_name == service_name,
            ServiceConfig.status == "published",
        )
    )
    row = result.scalar_one_or_none()
    if row is not None:
        set_cached_config(service_name, row)
    return row


async def get_config(session: AsyncSession, service_name: str) -> ServiceConfig | None:
    """Return the full ServiceConfig ORM object (any status), or None."""
    result = await session.execute(
        select(ServiceConfig).where(ServiceConfig.service_name == service_name)
    )
    return result.scalar_one_or_none()


async def list_configs(
    session: AsyncSession,
    status: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[ServiceConfig]:
    q = select(ServiceConfig).order_by(ServiceConfig.service_name)
    if status:
        q = q.where(ServiceConfig.status == status)
    q = q.offset(offset).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())


async def create_config(
    session: AsyncSession,
    service_name: str,
    slug: str,
    config: dict,
    changed_by: str | None = None,
) -> ServiceConfig:
    """Create a new service config with status='draft'."""
    obj = ServiceConfig(
        service_name=service_name,
        slug=slug,
        config=config,
        status="draft",
        version=1,
        updated_by=changed_by,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def update_config(
    session: AsyncSession,
    service_name: str,
    config: dict,
    changed_by: str | None = None,
    change_summary: str | None = None,
) -> ServiceConfig:
    """Update an existing config (increments version, saves history snapshot)."""
    obj = await get_config(session, service_name)
    if obj is None:
        raise ValueError(f"Service config not found: {service_name}")

    # Snapshot current state to history
    session.add(
        ServiceConfigHistory(
            service_config_id=obj.id,
            version=obj.version,
            config=obj.config,
            status=obj.status,
            changed_by=obj.updated_by,
            change_summary=change_summary,
        )
    )

    obj.config = config
    obj.version = obj.version + 1
    obj.updated_by = changed_by
    obj.updated_at = datetime.now(timezone.utc)
    # If currently published, revert to draft on update
    if obj.status == "published":
        obj.status = "draft"
        obj.published_at = None

    await session.commit()
    await session.refresh(obj)
    invalidate_cache(service_name)
    return obj


async def publish_config(
    session: AsyncSession,
    service_name: str,
    changed_by: str | None = None,
) -> ServiceConfig:
    """Move a config from draft to published status."""
    obj = await get_config(session, service_name)
    if obj is None:
        raise ValueError(f"Service config not found: {service_name}")
    obj.status = "published"
    obj.published_at = datetime.now(timezone.utc)
    obj.updated_by = changed_by
    obj.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(obj)
    invalidate_cache(service_name)
    return obj


async def archive_config(
    session: AsyncSession, service_name: str, changed_by: str | None = None
) -> ServiceConfig:
    """Soft-delete a config by setting status='archived'."""
    obj = await get_config(session, service_name)
    if obj is None:
        raise ValueError(f"Service config not found: {service_name}")
    obj.status = "archived"
    obj.updated_by = changed_by
    obj.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(obj)
    invalidate_cache(service_name)
    return obj


async def revert_config(
    session: AsyncSession,
    service_name: str,
    target_version: int,
    changed_by: str | None = None,
) -> ServiceConfig:
    """Revert a config to a historical version (creates a new version entry)."""
    obj = await get_config(session, service_name)
    if obj is None:
        raise ValueError(f"Service config not found: {service_name}")

    history_result = await session.execute(
        select(ServiceConfigHistory).where(
            ServiceConfigHistory.service_config_id == obj.id,
            ServiceConfigHistory.version == target_version,
        )
    )
    history_entry = history_result.scalar_one_or_none()
    if history_entry is None:
        raise ValueError(f"Version {target_version} not found for {service_name}")

    return await update_config(
        session,
        service_name,
        config=history_entry.config,
        changed_by=changed_by,
        change_summary=f"Reverted to version {target_version}",
    )


async def get_config_history(
    session: AsyncSession, service_name: str
) -> list[ServiceConfigHistory]:
    """Return all history entries for a config, newest first."""
    obj = await get_config(session, service_name)
    if obj is None:
        return []
    result = await session.execute(
        select(ServiceConfigHistory)
        .where(ServiceConfigHistory.service_config_id == obj.id)
        .order_by(ServiceConfigHistory.version.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Product Catalog CRUD
# ---------------------------------------------------------------------------


async def get_catalog(session: AsyncSession) -> list[ProductFamily]:
    """Return all families with their services, ordered by family.order."""
    result = await session.execute(
        select(ProductFamily)
        .options(selectinload(ProductFamily.services))
        .order_by(ProductFamily.order)
    )
    return list(result.scalars().all())


async def get_family(session: AsyncSession, key: str) -> ProductFamily | None:
    result = await session.execute(
        select(ProductFamily)
        .where(ProductFamily.key == key)
        .options(selectinload(ProductFamily.services))
    )
    return result.scalar_one_or_none()


async def create_family(
    session: AsyncSession, key: str, label: str, order: int = 0
) -> ProductFamily:
    obj = ProductFamily(key=key, label=label, order=order)
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def update_family(
    session: AsyncSession, key: str, label: str | None = None, order: int | None = None
) -> ProductFamily:
    obj = await get_family(session, key)
    if obj is None:
        raise ValueError(f"Family not found: {key}")
    if label is not None:
        obj.label = label
    if order is not None:
        obj.order = order
    await session.commit()
    await session.refresh(obj)
    return obj


async def delete_family(session: AsyncSession, key: str) -> None:
    obj = await get_family(session, key)
    if obj is None:
        raise ValueError(f"Family not found: {key}")
    if obj.services:
        raise ValueError(f"Cannot delete family '{key}' with existing services")
    await session.delete(obj)
    await session.commit()


async def get_service_entry(
    session: AsyncSession, service_name: str
) -> ProductService | None:
    result = await session.execute(
        select(ProductService).where(ProductService.service_name == service_name)
    )
    return result.scalar_one_or_none()


async def create_service_entry(
    session: AsyncSession,
    family_key: str,
    service_name: str,
    description: str = "",
    icon: str | None = None,
    popular: bool = False,
    display_name_cn: str | None = None,
    region_constraints: dict | None = None,
    order: int = 0,
) -> ProductService:
    family = await get_family(session, family_key)
    if family is None:
        raise ValueError(f"Family not found: {family_key}")
    obj = ProductService(
        family_id=family.id,
        service_name=service_name,
        description=description,
        icon=icon,
        popular=popular,
        display_name_cn=display_name_cn,
        region_constraints=region_constraints,
        order=order,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def update_service_entry(
    session: AsyncSession, service_name: str, **kwargs
) -> ProductService:
    obj = await get_service_entry(session, service_name)
    if obj is None:
        raise ValueError(f"Service not found: {service_name}")
    allowed = {"description", "icon", "popular", "display_name_cn", "region_constraints", "order"}
    for key, value in kwargs.items():
        if key in allowed:
            setattr(obj, key, value)
    await session.commit()
    await session.refresh(obj)
    return obj


async def delete_service_entry(session: AsyncSession, service_name: str) -> None:
    obj = await get_service_entry(session, service_name)
    if obj is None:
        raise ValueError(f"Service not found: {service_name}")
    await session.delete(obj)
    await session.commit()
