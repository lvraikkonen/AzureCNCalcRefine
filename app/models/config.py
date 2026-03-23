"""ORM models for product configuration management."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ServiceConfig(Base):
    """One row per product service configuration."""

    __tablename__ = "service_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    history: Mapped[list["ServiceConfigHistory"]] = relationship(
        "ServiceConfigHistory", back_populates="service_config", cascade="all, delete-orphan"
    )


class ServiceConfigHistory(Base):
    """Audit trail of all config changes."""

    __tablename__ = "service_config_history"
    __table_args__ = (UniqueConstraint("service_config_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("service_configs.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    service_config: Mapped["ServiceConfig"] = relationship(
        "ServiceConfig", back_populates="history"
    )


class ProductFamily(Base):
    """Product catalog families (e.g., Compute, Networking)."""

    __tablename__ = "product_families"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    services: Mapped[list["ProductService"]] = relationship(
        "ProductService", back_populates="family", cascade="all, delete-orphan",
        order_by="ProductService.order"
    )


class ProductService(Base):
    """Product services within a catalog family."""

    __tablename__ = "product_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("product_families.id", ondelete="CASCADE"), nullable=False
    )
    service_name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    icon: Mapped[str | None] = mapped_column(String(100), nullable=True)
    popular: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_name_cn: Mapped[str | None] = mapped_column(String(200), nullable=True)
    region_constraints: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    family: Mapped["ProductFamily"] = relationship("ProductFamily", back_populates="services")
