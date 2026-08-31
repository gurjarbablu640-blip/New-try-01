"""Add call_records table for Voice Intelligence & Call Analytics.

Revision ID: 20260903_call_records
Revises: 20260902_company_brain
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260903_call_records"
down_revision: Union[str, None] = "20260902_company_brain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "call_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id", ondelete="SET NULL"), nullable=True),
        sa.Column("salesperson_name", sa.String(length=100), server_default="Sales Rep", nullable=False),
        sa.Column("call_date", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("call_channel", sa.String(length=50), server_default="Phone", nullable=False),
        sa.Column("recording_file_url", sa.String(length=500), nullable=True),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("call_objective", sa.String(length=100), nullable=True),
        sa.Column("call_score", sa.Integer(), server_default="70", nullable=False),
        sa.Column("score_breakdown", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("buying_signals_detected", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("objections_detected", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extracted_facts", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("coaching_advice", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("outcome_status", sa.String(length=50), server_default="completed", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_call_records_id", "call_records", ["id"])
    op.create_index("ix_call_records_company_id", "call_records", ["company_id"])
    op.create_index("ix_call_records_person_id", "call_records", ["person_id"])
    op.create_index("ix_call_records_call_date", "call_records", ["call_date"])


def downgrade() -> None:
    op.drop_index("ix_call_records_call_date", table_name="call_records")
    op.drop_index("ix_call_records_person_id", table_name="call_records")
    op.drop_index("ix_call_records_company_id", table_name="call_records")
    op.drop_index("ix_call_records_id", table_name="call_records")
    op.drop_table("call_records")
