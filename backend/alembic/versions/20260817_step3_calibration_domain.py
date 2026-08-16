"""Step 3: Add Facility and CustomerAsset tables for calibration domain intelligence.

Revision ID: 20260817_step3_calibration_domain
Revises: 20260817_step1_lead_engine
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260817_step3_calib"
down_revision: Union[str, None] = "20260817_step1_lead_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create facilities table
    op.create_table(
        "facilities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("plant_code", sa.String(length=100), nullable=True),
        sa.Column("industrial_estate", sa.String(length=300), nullable=True),
        sa.Column("city", sa.String(length=200), nullable=True),
        sa.Column("state", sa.String(length=200), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_facilities_id", "facilities", ["id"], unique=False)
    op.create_index("ix_facilities_company_id", "facilities", ["company_id"], unique=False)
    op.create_index("ix_facilities_name", "facilities", ["name"], unique=False)
    op.create_index("ix_facilities_plant_code", "facilities", ["plant_code"], unique=False)

    # 2. Create customer_assets table
    op.create_table(
        "customer_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.Integer(), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("asset_tag", sa.String(length=200), nullable=True),
        sa.Column("serial_number", sa.String(length=200), nullable=True),
        sa.Column("instrument_name", sa.String(length=500), nullable=False),
        sa.Column("make", sa.String(length=300), nullable=True),
        sa.Column("model", sa.String(length=300), nullable=True),
        sa.Column("parameter", sa.String(length=300), nullable=True),
        sa.Column("range_value", sa.String(length=300), nullable=True),
        sa.Column("location_in_plant", sa.String(length=300), nullable=True),
        sa.Column("last_calibrated_date", sa.Date(), nullable=True),
        sa.Column("calibration_due_date", sa.Date(), nullable=True),
        sa.Column("calibration_interval_months", sa.Integer(), server_default="12", nullable=False),
        sa.Column("certificate_number", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="Active", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_assets_id", "customer_assets", ["id"], unique=False)
    op.create_index("ix_customer_assets_company_id", "customer_assets", ["company_id"], unique=False)
    op.create_index("ix_customer_assets_facility_id", "customer_assets", ["facility_id"], unique=False)
    op.create_index("ix_customer_assets_instrument_id", "customer_assets", ["instrument_id"], unique=False)
    op.create_index("ix_customer_assets_asset_tag", "customer_assets", ["asset_tag"], unique=False)
    op.create_index("ix_customer_assets_serial_number", "customer_assets", ["serial_number"], unique=False)
    op.create_index("ix_customer_assets_instrument_name", "customer_assets", ["instrument_name"], unique=False)
    op.create_index("ix_customer_assets_calibration_due_date", "customer_assets", ["calibration_due_date"], unique=False)
    op.create_index("ix_customer_assets_status", "customer_assets", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_customer_assets_status", table_name="customer_assets")
    op.drop_index("ix_customer_assets_calibration_due_date", table_name="customer_assets")
    op.drop_index("ix_customer_assets_instrument_name", table_name="customer_assets")
    op.drop_index("ix_customer_assets_serial_number", table_name="customer_assets")
    op.drop_index("ix_customer_assets_asset_tag", table_name="customer_assets")
    op.drop_index("ix_customer_assets_instrument_id", table_name="customer_assets")
    op.drop_index("ix_customer_assets_facility_id", table_name="customer_assets")
    op.drop_index("ix_customer_assets_company_id", table_name="customer_assets")
    op.drop_index("ix_customer_assets_id", table_name="customer_assets")
    op.drop_table("customer_assets")

    op.drop_index("ix_facilities_plant_code", table_name="facilities")
    op.drop_index("ix_facilities_name", table_name="facilities")
    op.drop_index("ix_facilities_company_id", table_name="facilities")
    op.drop_index("ix_facilities_id", table_name="facilities")
    op.drop_table("facilities")
