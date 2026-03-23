"""Pydantic request/response schemas for the Admin API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Service Config schemas
# ---------------------------------------------------------------------------


class ServiceConfigCreate(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=200)
    slug: str | None = Field(None, max_length=200)
    config: dict[str, Any] = Field(default_factory=dict)
    changed_by: str | None = None

    @field_validator("slug", mode="before")
    @classmethod
    def derive_slug(cls, v, info):
        if v:
            return v
        service_name = info.data.get("service_name", "")
        return service_name.lower().replace(" ", "_")


class ServiceConfigUpdate(BaseModel):
    config: dict[str, Any]
    changed_by: str | None = None
    change_summary: str | None = None


class ServiceConfigPublish(BaseModel):
    changed_by: str | None = None


class ServiceConfigRevert(BaseModel):
    changed_by: str | None = None


class ServiceConfigValidate(BaseModel):
    config: dict[str, Any]


class ServiceConfigResponse(BaseModel):
    id: int
    service_name: str
    slug: str
    config: dict[str, Any]
    status: str
    version: int
    updated_by: str | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None

    model_config = {"from_attributes": True}


class ServiceConfigListItem(BaseModel):
    id: int
    service_name: str
    slug: str
    status: str
    version: int
    updated_by: str | None
    updated_at: datetime
    published_at: datetime | None

    model_config = {"from_attributes": True}


class ServiceConfigHistoryItem(BaseModel):
    id: int
    version: int
    config: dict[str, Any]
    status: str
    changed_by: str | None
    change_summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Product Catalog schemas
# ---------------------------------------------------------------------------


class FamilyCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    label: str = Field(..., min_length=1, max_length=200)
    order: int = 0


class FamilyUpdate(BaseModel):
    label: str | None = Field(None, max_length=200)
    order: int | None = None


class ServiceEntryCreate(BaseModel):
    family_key: str
    service_name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    icon: str | None = None
    popular: bool = False
    display_name_cn: str | None = None
    region_constraints: dict | None = None
    order: int = 0


class ServiceEntryUpdate(BaseModel):
    description: str | None = None
    icon: str | None = None
    popular: bool | None = None
    display_name_cn: str | None = None
    region_constraints: dict | None = None
    order: int | None = None


class ReorderItem(BaseModel):
    key: str  # family key or service_name
    order: int


class ReorderRequest(BaseModel):
    families: list[ReorderItem] | None = None
    services: list[ReorderItem] | None = None  # service_name → order


class ServiceEntryResponse(BaseModel):
    id: int
    family_id: int
    service_name: str
    description: str
    icon: str | None
    popular: bool
    display_name_cn: str | None
    region_constraints: dict | None
    order: int

    model_config = {"from_attributes": True}


class FamilyResponse(BaseModel):
    id: int
    key: str
    label: str
    order: int
    services: list[ServiceEntryResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Bulk import schemas
# ---------------------------------------------------------------------------


class ImportJsonFilesRequest(BaseModel):
    overwrite: bool = False


class ImportResult(BaseModel):
    action: Literal["created", "updated", "skipped", "error"]
    service_name: str
    detail: str | None = None


class ImportResponse(BaseModel):
    results: list[ImportResult]
    total: int
    created: int
    updated: int
    skipped: int
    errors: int
