"""Create config management tables

Revision ID: 0001
Revises:
Create Date: 2026-03-23

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("config", JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("service_name", name="uq_service_configs_service_name"),
        sa.UniqueConstraint("slug", name="uq_service_configs_slug"),
    )
    op.create_index("ix_service_configs_status", "service_configs", ["status"])

    op.create_table(
        "service_config_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "service_config_id",
            sa.Integer(),
            sa.ForeignKey("service_configs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config", JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("changed_by", sa.String(100), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "service_config_id", "version", name="uq_config_history_id_version"
        ),
    )
    op.create_index(
        "ix_config_history_service_config_id",
        "service_config_history",
        ["service_config_id"],
    )

    op.create_table(
        "product_families",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("key", name="uq_product_families_key"),
    )

    op.create_table(
        "product_services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "family_id",
            sa.Integer(),
            sa.ForeignKey("product_families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("service_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("icon", sa.String(100), nullable=True),
        sa.Column("popular", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("display_name_cn", sa.String(200), nullable=True),
        sa.Column("region_constraints", JSONB(), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("service_name", name="uq_product_services_service_name"),
    )
    op.create_index(
        "ix_product_services_family_id", "product_services", ["family_id"]
    )


def downgrade() -> None:
    op.drop_table("product_services")
    op.drop_table("product_families")
    op.drop_table("service_config_history")
    op.drop_table("service_configs")
