"""Add 12 Sales OS performance indexes post-merge.

Revision ID: add_salesos_perf_idx_2026
Revises: merge_heads_2026
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "add_salesos_perf_idx_2026"
down_revision: Union[str, None] = "merge_heads_2026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_opportunities_person_id", "opportunities", ["person_id"])
    op.create_index("ix_sales_tasks_company_id", "sales_tasks", ["company_id"])
    op.create_index("ix_sales_tasks_opportunity_id", "sales_tasks", ["opportunity_id"])
    op.create_index("ix_sales_notes_company_id", "sales_notes", ["company_id"])
    op.create_index("ix_instruments_parameter", "instruments", ["parameter"])
    op.create_index("ix_quotations_company_id", "quotations", ["company_id"])
    op.create_index("ix_quotation_items_quotation_id", "quotation_items", ["quotation_id"])
    op.create_index("ix_price_history_instrument_id", "price_history", ["instrument_id"])
    op.create_index("ix_price_history_customer_name", "price_history", ["customer_name"])
    op.create_index("ix_ai_feedback_entity_type", "ai_feedback", ["entity_type"])
    op.create_index("ix_ai_feedback_entity_id", "ai_feedback", ["entity_id"])
    op.create_index("ix_learning_rules_rule_type", "learning_rules", ["rule_type"])


def downgrade() -> None:
    op.drop_index("ix_learning_rules_rule_type", table_name="learning_rules")
    op.drop_index("ix_ai_feedback_entity_id", table_name="ai_feedback")
    op.drop_index("ix_ai_feedback_entity_type", table_name="ai_feedback")
    op.drop_index("ix_price_history_customer_name", table_name="price_history")
    op.drop_index("ix_price_history_instrument_id", table_name="price_history")
    op.drop_index("ix_quotation_items_quotation_id", table_name="quotation_items")
    op.drop_index("ix_quotations_company_id", table_name="quotations")
    op.drop_index("ix_instruments_parameter", table_name="instruments")
    op.drop_index("ix_sales_notes_company_id", table_name="sales_notes")
    op.drop_index("ix_sales_tasks_opportunity_id", table_name="sales_tasks")
    op.drop_index("ix_sales_tasks_company_id", table_name="sales_tasks")
    op.drop_index("ix_opportunities_person_id", table_name="opportunities")
