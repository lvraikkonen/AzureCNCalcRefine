"""Schemas for the product configuration (cascading filter) API."""

from pydantic import BaseModel


class SubDimensionOption(BaseModel):
    """A single option within a sub-dimension dropdown."""

    value: str
    label: str | None = None


class SubDimension(BaseModel):
    """A sub-dimension extracted from a compound dimension value.

    For example, VM productName "Virtual Machines Dv5 Series Windows" yields
    sub-dimensions: os=Windows, deployment=Virtual Machines, category=General Purpose,
    instance_series=Dv5.
    """

    field: str  # e.g. "os", "category", "instance_series"
    label: str  # e.g. "Operating System"
    options: list[SubDimensionOption]
    selected: str | None = None
    order: int


class DimensionResponse(BaseModel):
    """A single cascade dimension with its available options."""

    field: str  # e.g. "arm_region_name", "product_name"
    label: str  # e.g. "Region", "Product"
    options: list[str]
    selected: str | None = None
    visible: bool = True
    sub_dimensions: list[SubDimension] | None = None


class ConfigurationResponse(BaseModel):
    """Response from the configurations endpoint."""

    service_name: str
    dimensions: list[DimensionResponse]


class ConfigurationRequest(BaseModel):
    """Request body for the configurations endpoint."""

    selections: dict[str, str] = {}
    sub_selections: dict[str, dict[str, str]] | None = None
