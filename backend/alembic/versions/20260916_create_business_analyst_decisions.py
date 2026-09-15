"""Create business_analyst_decisions table and attribution FKs.

Revision ID: 20260916_ba_decisions
Revises: 20260916_discovery_logs
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260916_ba_decisions"
down_revision: Union[str, None] = "20260916_discovery_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. Create business_analyst_decisions table
    if "business_analyst_decisions" not in tables:
        op.create_table(
            "business_analyst_decisions",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False, index=True),
            sa.Column("sector", sa.String(length=100), nullable=False, index=True),
            sa.Column("trigger_family", sa.String(length=100), nullable=False, index=True),
            sa.Column("geography", sa.String(length=100), nullable=False, index=True),
            sa.Column("mode", sa.String(length=50), server_default="EXPLOIT", nullable=False, index=True),
            sa.Column("priority_score", sa.Float(), server_default="0.0", nullable=False),
            sa.Column("confidence", sa.Float(), server_default="0.0", nullable=False),
            sa.Column("search_budget", sa.Integer(), server_default="3", nullable=False),
            # Raw Counts
            sa.Column("historical_query_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("productive_query_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("strong_opportunities", sa.Integer(), server_default="0", nullable=False),
            sa.Column("incomplete_opportunities", sa.Integer(), server_default="0", nullable=False),
            sa.Column("apollo_reached", sa.Integer(), server_default="0", nullable=False),
            sa.Column("person_passes", sa.Integer(), server_default="0", nullable=False),
            sa.Column("emails_sent", sa.Integer(), server_default="0", nullable=False),
            sa.Column("replies", sa.Integer(), server_default="0", nullable=False),
            sa.Column("enquiries", sa.Integer(), server_default="0", nullable=False),
            # Normalized Rates
            sa.Column("productive_query_rate", sa.Float(), server_default="0.0", nullable=False),
            sa.Column("strong_per_query", sa.Float(), server_default="0.0", nullable=False),
            sa.Column("apollo_per_query", sa.Float(), server_default="0.0", nullable=False),
            sa.Column("person_pass_per_query", sa.Float(), server_default="0.0", nullable=False),
            sa.Column("email_per_query", sa.Float(), server_default="0.0", nullable=False),
            sa.Column("reply_per_email", sa.Float(), server_default="0.0", nullable=False),
            sa.Column("enquiry_per_query", sa.Float(), server_default="0.0", nullable=False),
            sa.Column("enquiry_per_email", sa.Float(), server_default="0.0", nullable=False),
            # Strategy Rationale & Metadata
            sa.Column("score_components", sa.JSON(), nullable=True),
            sa.Column("rationale", sa.Text(), nullable=True),
            # Substitution Tracking
            sa.Column("was_substituted", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("substitution_reason", sa.Text(), nullable=True),
            sa.Column("actual_sector", sa.String(length=100), nullable=True),
            sa.Column("actual_trigger", sa.String(length=100), nullable=True),
            sa.Column("actual_geography", sa.String(length=100), nullable=True),
            # Downstream final outcomes
            sa.Column("final_outcomes_json", sa.JSON(), nullable=True),
        )
        op.create_index(
            "ix_analyst_decision_sector_trigger_geo",
            "business_analyst_decisions",
            ["sector", "trigger_family", "geography"],
        )
        op.create_index(
            "ix_analyst_decision_mode_created",
            "business_analyst_decisions",
            ["mode", "created_at"],
        )

    # 2. Add analyst_decision_id to discovery_query_logs
    dq_columns = [col["name"] for col in inspector.get_columns("discovery_query_logs")]
    if "analyst_decision_id" not in dq_columns:
        op.add_column(
            "discovery_query_logs",
            sa.Column("analyst_decision_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_discovery_query_logs_analyst_decision_id",
            "discovery_query_logs",
            "business_analyst_decisions",
            ["analyst_decision_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_discovery_query_logs_analyst_decision_id",
            "discovery_query_logs",
            ["analyst_decision_id"],
        )

    # 3. Add discovery_query_log_id and analyst_decision_id to companies
    co_columns = [col["name"] for col in inspector.get_columns("companies")]
    if "discovery_query_log_id" not in co_columns:
        op.add_column(
            "companies",
            sa.Column("discovery_query_log_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_companies_discovery_query_log_id",
            "companies",
            "discovery_query_logs",
            ["discovery_query_log_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_companies_discovery_query_log_id",
            "companies",
            ["discovery_query_log_id"],
        )

    if "analyst_decision_id" not in co_columns:
        op.add_column(
            "companies",
            sa.Column("analyst_decision_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_companies_analyst_decision_id",
            "companies",
            "business_analyst_decisions",
            ["analyst_decision_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_companies_analyst_decision_id",
            "companies",
            ["analyst_decision_id"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    co_columns = [col["name"] for col in inspector.get_columns("companies")]
    if "analyst_decision_id" in co_columns:
        op.drop_constraint("fk_companies_analyst_decision_id", "companies", type_="foreignkey")
        op.drop_index("ix_companies_analyst_decision_id", table_name="companies")
        op.drop_column("companies", "analyst_decision_id")
    if "discovery_query_log_id" in co_columns:
        op.drop_constraint("fk_companies_discovery_query_log_id", "companies", type_="foreignkey")
        op.drop_index("ix_companies_discovery_query_log_id", table_name="companies")
        op.drop_column("companies", "discovery_query_log_id")

    dq_columns = [col["name"] for col in inspector.get_columns("discovery_query_logs")]
    if "analyst_decision_id" in dq_columns:
        op.drop_constraint("fk_discovery_query_logs_analyst_decision_id", "discovery_query_logs", type_="foreignkey")
        op.drop_index("ix_discovery_query_logs_analyst_decision_id", table_name="discovery_query_logs")
        op.drop_column("discovery_query_logs", "analyst_decision_id")

    tables = inspector.get_table_names()
    if "business_analyst_decisions" in tables:
        op.drop_table("business_analyst_decisions")
