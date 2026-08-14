"""Add Oorja Sales OS foundation tables.

Revision ID: 20260814_sales_os
Revises: 9073563ba3cc
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260814_sales_os"
down_revision: Union[str, None] = "9073563ba3cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Neutralized duplicate: Sales OS table creation is handled by the canonical migration
    # 9b21d4a6c1f2. This upgrade is intentionally a no-op to avoid duplicate CREATE TABLE
    # attempts on a fresh database where the canonical migration will also run.
    return

x_quotation_items_quotation_id", "quotation_items", ["quotation_id"])
    op.create_index("ix_quotation_items_normalized_name", "quotation_items", ["normalized_name"])

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id", ondelete="SET NULL")),
        sa.Column("customer_name", sa.String(500)),
        sa.Column("quotation_id", sa.Integer(), sa.ForeignKey("quotations.id", ondelete="SET NULL")),
        sa.Column("calibration_type", sa.String(100)),
        sa.Column("location", sa.String(300)),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("quotation_date", sa.Date()),
        sa.Column("outcome", sa.String(50)),
        sa.Column("context", JSONB),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_price_history_instrument_id", "price_history", ["instrument_id"])
    op.create_index("ix_price_history_customer_name", "price_history", ["customer_name"])

    op.create_table(
        "ai_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("ai_value", JSONB),
        sa.Column("human_value", JSONB),
        sa.Column("reason", sa.Text()),
        sa.Column("outcome", sa.String(100)),
        sa.Column("confidence", sa.Numeric(5, 2)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_feedback_entity_type", "ai_feedback", ["entity_type"])
    op.create_index("ix_ai_feedback_entity_id", "ai_feedback", ["entity_id"])

    op.create_table(
        "learning_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_type", sa.String(100), nullable=False),
        sa.Column("rule_key", sa.String(300), nullable=False),
        sa.Column("pattern", JSONB, nullable=False),
        sa.Column("evidence_count", sa.Integer(), server_default="0"),
        sa.Column("confidence", sa.Numeric(5, 2), server_default="0"),
        sa.Column("status", sa.String(50), server_default="Candidate"),
        sa.Column("approved_by", sa.String(200)),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_learning_rules_rule_type", "learning_rules", ["rule_type"])
    op.create_index("ix_learning_rules_status", "learning_rules", ["status"])


def downgrade() -> None:
    # Conservative downgrade: do not drop canonical tables. This migration has been
    # neutralized to avoid destructive operations in environments where canonical
    # migrations created the objects.
    return
