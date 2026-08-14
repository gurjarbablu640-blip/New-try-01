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
    op.create_table(
        "opportunities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("stage", sa.String(100), nullable=False, server_default="New"),
        sa.Column("probability", sa.Numeric(5, 2), server_default="0"),
        sa.Column("estimated_value", sa.Numeric(14, 2), server_default="0"),
        sa.Column("expected_close_date", sa.Date()),
        sa.Column("source", sa.String(100)),
        sa.Column("loss_reason", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("ai_summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_opportunities_company_id", "opportunities", ["company_id"])
    op.create_index("ix_opportunities_person_id", "opportunities", ["person_id"])
    op.create_index("ix_opportunities_stage", "opportunities", ["stage"])

    op.create_table(
        "sales_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE")),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id", ondelete="CASCADE")),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("task_type", sa.String(100), server_default="Follow-up"),
        sa.Column("priority", sa.String(30), server_default="Medium"),
        sa.Column("status", sa.String(30), server_default="Open"),
        sa.Column("due_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("source", sa.String(100), server_default="manual"),
        sa.Column("ai_reason", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_sales_tasks_company_id", "sales_tasks", ["company_id"])
    op.create_index("ix_sales_tasks_opportunity_id", "sales_tasks", ["opportunity_id"])
    op.create_index("ix_sales_tasks_due_at", "sales_tasks", ["due_at"])
    op.create_index("ix_sales_tasks_status", "sales_tasks", ["status"])

    op.create_table(
        "sales_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id", ondelete="SET NULL")),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id", ondelete="SET NULL")),
        sa.Column("note_type", sa.String(100), server_default="General"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source", sa.String(100), server_default="user"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_sales_notes_company_id", "sales_notes", ["company_id"])

    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family", sa.String(300), nullable=False),
        sa.Column("parameter", sa.String(300)),
        sa.Column("make", sa.String(300)),
        sa.Column("model", sa.String(300)),
        sa.Column("range_value", sa.String(300)),
        sa.Column("unit", sa.String(100)),
        sa.Column("calibration_requirement", sa.Text()),
        sa.Column("nabl_applicable", sa.Integer()),
        sa.Column("metadata_json", JSONB),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_instruments_family", "instruments", ["family"])
    op.create_index("ix_instruments_parameter", "instruments", ["parameter"])

    op.create_table(
        "instrument_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(500), nullable=False),
        sa.Column("source", sa.String(100), server_default="user"),
        sa.Column("confidence", sa.Numeric(5, 2), server_default="100"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_instrument_aliases_alias", "instrument_aliases", ["alias"])

    op.create_table(
        "quotations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="SET NULL")),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id", ondelete="SET NULL")),
        sa.Column("quotation_number", sa.String(100), unique=True),
        sa.Column("quotation_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date()),
        sa.Column("customer_name", sa.String(500), nullable=False),
        sa.Column("location", sa.String(300)),
        sa.Column("calibration_type", sa.String(100)),
        sa.Column("subtotal", sa.Numeric(14, 2), server_default="0"),
        sa.Column("discount", sa.Numeric(14, 2), server_default="0"),
        sa.Column("tax", sa.Numeric(14, 2), server_default="0"),
        sa.Column("total", sa.Numeric(14, 2), server_default="0"),
        sa.Column("status", sa.String(50), server_default="Draft"),
        sa.Column("source_file", sa.String(1000)),
        sa.Column("ai_recommendation", JSONB),
        sa.Column("human_approved", sa.Integer(), server_default="0"),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_quotations_company_id", "quotations", ["company_id"])
    op.create_index("ix_quotations_status", "quotations", ["status"])

    op.create_table(
        "quotation_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("quotation_id", sa.Integer(), sa.ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id", ondelete="SET NULL")),
        sa.Column("instrument_name", sa.String(500), nullable=False),
        sa.Column("normalized_name", sa.String(500)),
        sa.Column("make", sa.String(300)),
        sa.Column("model", sa.String(300)),
        sa.Column("range_value", sa.String(300)),
        sa.Column("parameter", sa.String(300)),
        sa.Column("quantity", sa.Numeric(12, 3), server_default="1"),
        sa.Column("onsite", sa.Integer(), server_default="0"),
        sa.Column("unit_price", sa.Numeric(14, 2), server_default="0"),
        sa.Column("total_price", sa.Numeric(14, 2), server_default="0"),
        sa.Column("nabl_applicable", sa.Integer()),
        sa.Column("nabl_validated", sa.Integer(), server_default="0"),
        sa.Column("price_source", sa.String(100)),
        sa.Column("ai_confidence", sa.Numeric(5, 2)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_quotation_items_quotation_id", "quotation_items", ["quotation_id"])
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
    for table in [
        "learning_rules",
        "ai_feedback",
        "price_history",
        "quotation_items",
        "quotations",
        "instrument_aliases",
        "instruments",
        "sales_notes",
        "sales_tasks",
        "opportunities",
    ]:
        op.drop_table(table)
