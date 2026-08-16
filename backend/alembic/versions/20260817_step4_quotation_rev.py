"""Step 4: Add quotation versioning, facility and customer asset linkages.

Revision ID: 20260817_step4_quotation_rev
Revises: 20260817_step3_calib
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260817_step4_quotation_rev"
down_revision: Union[str, None] = "20260817_step3_calib"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add columns to quotations table
    op.add_column("quotations", sa.Column("parent_quotation_id", sa.Integer(), sa.ForeignKey("quotations.id", ondelete="SET NULL"), nullable=True))
    op.add_column("quotations", sa.Column("facility_id", sa.Integer(), sa.ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True))
    op.add_column("quotations", sa.Column("version_number", sa.Integer(), server_default="1", nullable=False))
    op.add_column("quotations", sa.Column("is_latest", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    op.add_column("quotations", sa.Column("revision_notes", sa.Text(), nullable=True))

    op.create_index("ix_quotations_parent_quotation_id", "quotations", ["parent_quotation_id"], unique=False)
    op.create_index("ix_quotations_facility_id", "quotations", ["facility_id"], unique=False)
    op.create_index("ix_quotations_version_number", "quotations", ["version_number"], unique=False)
    op.create_index("ix_quotations_is_latest", "quotations", ["is_latest"], unique=False)

    # 2. Add columns to quotation_items table
    op.add_column("quotation_items", sa.Column("customer_asset_id", sa.Integer(), sa.ForeignKey("customer_assets.id", ondelete="SET NULL"), nullable=True))
    op.add_column("quotation_items", sa.Column("nabl_fit_status", sa.String(length=50), nullable=True))

    op.create_index("ix_quotation_items_customer_asset_id", "quotation_items", ["customer_asset_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_quotation_items_customer_asset_id", table_name="quotation_items")
    op.drop_column("quotation_items", "nabl_fit_status")
    op.drop_column("quotation_items", "customer_asset_id")

    op.drop_index("ix_quotations_is_latest", table_name="quotations")
    op.drop_index("ix_quotations_version_number", table_name="quotations")
    op.drop_index("ix_quotations_facility_id", table_name="quotations")
    op.drop_index("ix_quotations_parent_quotation_id", table_name="quotations")
    op.drop_column("quotations", "revision_notes")
    op.drop_column("quotations", "is_latest")
    op.drop_column("quotations", "version_number")
    op.drop_column("quotations", "facility_id")
    op.drop_column("quotations", "parent_quotation_id")
