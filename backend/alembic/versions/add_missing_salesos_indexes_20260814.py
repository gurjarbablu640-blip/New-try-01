"""Add missing Sales OS indexes conditionally.

Revision ID: add_missing_salesos_indexes_20260814
Revises: merge_salesos_20260814
"""
from alembic import op
import sqlalchemy as sa

revision = "add_missing_salesos_idx"
down_revision = "merge_salesos_20260814"
branch_labels = None
depends_on = None


def upgrade():
    # Create indexes only if they do not already exist.
    statements = [
        "CREATE INDEX IF NOT EXISTS ix_opportunities_person_id ON opportunities (person_id);",
        "CREATE INDEX IF NOT EXISTS ix_sales_tasks_company_id ON sales_tasks (company_id);",
        "CREATE INDEX IF NOT EXISTS ix_sales_tasks_opportunity_id ON sales_tasks (opportunity_id);",
        "CREATE INDEX IF NOT EXISTS ix_sales_notes_company_id ON sales_notes (company_id);",
        "CREATE INDEX IF NOT EXISTS ix_instruments_parameter ON instruments (parameter);",
        "CREATE INDEX IF NOT EXISTS ix_quotations_company_id ON quotations (company_id);",
        "CREATE INDEX IF NOT EXISTS ix_quotation_items_quotation_id ON quotation_items (quotation_id);",
        "CREATE INDEX IF NOT EXISTS ix_price_history_instrument_id ON price_history (instrument_id);",
        "CREATE INDEX IF NOT EXISTS ix_price_history_customer_name ON price_history (customer_name);",
        "CREATE INDEX IF NOT EXISTS ix_ai_feedback_entity_type ON ai_feedback (entity_type);",
        "CREATE INDEX IF NOT EXISTS ix_ai_feedback_entity_id ON ai_feedback (entity_id);",
        "CREATE INDEX IF NOT EXISTS ix_learning_rules_rule_type ON learning_rules (rule_type);",
        "CREATE INDEX IF NOT EXISTS ix_learning_rules_rule_key ON learning_rules (rule_key);",
    ]
    conn = op.get_bind()
    for stmt in statements:
        conn.execute(sa.text(stmt))


def downgrade():
    # Do not drop indexes in downgrade to avoid accidental data/schema loss.
    raise NotImplementedError("Downgrade of add_missing_salesos_indexes_20260814 is not supported.")
