"""Add conversation memory tables (conversation_sessions, conversation_turns).

Revision ID: 20260901_conv_memory
Revises: 20260817_step4_quotation_rev
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260901_conv_memory"
down_revision: Union[str, None] = "20260817_step4_quotation_rev"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create conversation_sessions table
    op.create_table(
        "conversation_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("turn_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("context_snapshot", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
    )
    op.create_index("ix_conversation_sessions_status", "conversation_sessions", ["status"])

    # 2. Create conversation_turns table
    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("agent_name", sa.String(length=50), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reasoning_trace", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("iteration_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("tokens_used", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_conversation_turns_id", "conversation_turns", ["id"])
    op.create_index("ix_conversation_turns_session_id", "conversation_turns", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_conversation_turns_session_id", table_name="conversation_turns")
    op.drop_index("ix_conversation_turns_id", table_name="conversation_turns")
    op.drop_table("conversation_turns")
    op.drop_index("ix_conversation_sessions_status", table_name="conversation_sessions")
    op.drop_table("conversation_sessions")
