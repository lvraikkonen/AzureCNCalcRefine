"""Create retail_prices table for CN pricing data

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-03

"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retail_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("currency_code", sa.String(10), nullable=False, server_default="CNY"),
        sa.Column("tier_minimum_units", sa.Float(), nullable=False, server_default="0"),
        sa.Column("retail_price", sa.Float(), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("arm_region_name", sa.String(100), nullable=True),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("effective_start_date", sa.String(50), nullable=True),
        sa.Column("meter_id", sa.String(100), nullable=True),
        sa.Column("meter_name", sa.String(500), nullable=True),
        sa.Column("product_id", sa.String(100), nullable=True),
        sa.Column("sku_id", sa.String(100), nullable=True),
        sa.Column("product_name", sa.String(500), nullable=True),
        sa.Column("sku_name", sa.String(500), nullable=True),
        sa.Column("service_name", sa.String(300), nullable=True),
        sa.Column("service_family", sa.String(200), nullable=True),
        sa.Column("unit_of_measure", sa.String(100), nullable=True),
        sa.Column("type", sa.String(50), nullable=True),
        sa.Column("arm_sku_name", sa.String(200), nullable=True),
        sa.Column("term", sa.String(50), nullable=True),
        sa.Column("is_primary_meter_region", sa.Boolean(), nullable=True),
    )

    # Single-column indexes for common filters
    op.create_index("ix_rp_service_name", "retail_prices", ["service_name"])
    op.create_index("ix_rp_arm_region_name", "retail_prices", ["arm_region_name"])
    op.create_index("ix_rp_product_name", "retail_prices", ["product_name"])
    op.create_index("ix_rp_sku_name", "retail_prices", ["sku_name"])
    op.create_index("ix_rp_type", "retail_prices", ["type"])

    # Composite indexes for cascade query patterns
    op.create_index("ix_rp_service_region", "retail_prices", ["service_name", "arm_region_name"])
    op.create_index(
        "ix_rp_cascade",
        "retail_prices",
        ["service_name", "arm_region_name", "product_name", "sku_name", "type"],
    )


def downgrade() -> None:
    op.drop_table("retail_prices")
