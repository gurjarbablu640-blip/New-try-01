"""Create followup_query_memory_records table for Task 3D.1F.

Revision ID: 20260917_followup_memory
Revises: 20260916_ba_decisions
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260917_followup_memory"
down_revision: Union[str, None] = "20260916_ba_decisions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "followup_query_memory_records" not in tables:
        json_type = sa.JSON().with_variant(postgresql.JSONB, "postgresql")

        op.create_table(
            "followup_query_memory_records",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column(
                "company_id",
                sa.Integer(),
                sa.ForeignKey("companies.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column("normalized_operating_entity", sa.String(length=255), nullable=False, index=True),
            sa.Column("missing_fact", sa.String(length=100), nullable=False, index=True),
            sa.Column("query", sa.Text(), nullable=False),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
                index=True,
            ),
            sa.Column("research_strategy", sa.String(length=50), server_default="GENERAL_WEB", nullable=False),
            sa.Column("result_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("useful_urls", json_type, server_default="[]", nullable=False),
            sa.Column("new_evidence_found", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("evidence_type_found", sa.String(length=100), nullable=True),
            sa.Column("source_domains", json_type, server_default="[]", nullable=False),
            sa.Column("funnel_state_before", sa.String(length=50), nullable=True),
            sa.Column("funnel_state_after", sa.String(length=50), nullable=True),
            sa.Column("llm_reasoning", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )

        op.create_index(
            "ix_followup_entity_fact",
            "followup_query_memory_records",
            ["normalized_operating_entity", "missing_fact", "timestamp"],
        )
        op.create_index(
            "ix_followup_company_fact",
            "followup_query_memory_records",
            ["company_id", "missing_fact"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "followup_query_memory_records" in tables:
        indices = [idx["name"] for idx in inspector.get_indexes("followup_query_memory_records")]
        if "ix_followup_company_fact" in indices:
            op.drop_index("ix_followup_company_fact", table_name="followup_query_memory_records")
        if "ix_followup_entity_fact" in indices:
            op.drop_index("ix_followup_entity_fact", table_name="followup_query_memory_records")
        op.drop_table("followup_query_memory_records")
