"""Create discovery_query_logs table.

Revision ID: 20260916_discovery_logs
Revises: merge_heads_2026
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260916_discovery_logs"
down_revision: Union[str, None] = "20260904_reasoning_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use checkfirst or inspect table existence to avoid duplicate creation
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "discovery_query_logs" not in tables:
        op.create_table(
            "discovery_query_logs",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("query", sa.Text(), nullable=False),
            sa.Column("normalized_query", sa.String(length=500), nullable=False, index=True),
            sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("sector", sa.String(length=100), nullable=True, index=True),
            sa.Column("trigger", sa.String(length=100), nullable=True, index=True),
            sa.Column("geography", sa.String(length=100), nullable=True, index=True),
            sa.Column("execution_state", sa.String(length=50), nullable=False, server_default="SUCCESS_PRODUCTIVE", index=True),
            sa.Column("executed_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False, index=True),
            sa.Column("results_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("unique_results", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("new_companies", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("strong_opportunities", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("incomplete_opportunities", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("weak_opportunities", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("yield_score", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("exhaustion_score", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
        )
        op.create_index(
            "ix_discovery_query_page_time",
            "discovery_query_logs",
            ["normalized_query", "page", "executed_at"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "discovery_query_logs" in tables:
        op.drop_table("discovery_query_logs")
