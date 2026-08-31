"""Add company_belief_states and signal_evidence_nodes for Reasoning Foundation.

Revision ID: 20260904_reasoning_foundation
Revises: 20260903_call_records
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260904_reasoning_foundation"
down_revision: Union[str, None] = "20260903_call_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Company Belief States
    op.create_table(
        "company_belief_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("beliefs", JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("contradictions", JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("causal_traces", JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("active_research_tasks", JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("overall_confidence", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("last_reasoned_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_company_belief_states_id", "company_belief_states", ["id"])
    op.create_index("ix_company_belief_states_company_id", "company_belief_states", ["company_id"])

    # 2. Signal Evidence Nodes
    op.create_table(
        "signal_evidence_nodes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("epistemic_type", sa.String(length=50), server_default="INFERENCE", nullable=False),
        sa.Column("signal_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("source_reliability", sa.Float(), server_default="0.8", nullable=False),
        sa.Column("event_time", sa.DateTime(), nullable=True),
        sa.Column("detection_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("activation_window", sa.String(length=50), server_default="30_days", nullable=False),
        sa.Column("staleness_threshold_days", sa.Integer(), server_default="90", nullable=False),
        sa.Column("decay_rate", sa.Float(), server_default="0.01", nullable=False),
        sa.Column("current_effective_confidence", sa.Float(), server_default="0.8", nullable=False),
        sa.Column("causal_template_key", sa.String(length=100), nullable=True),
        sa.Column("is_contradicted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("evidence_metadata", JSONB(astext_type=sa.Text()), nullable=True, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_signal_evidence_nodes_id", "signal_evidence_nodes", ["id"])
    op.create_index("ix_signal_evidence_nodes_company_id", "signal_evidence_nodes", ["company_id"])
    op.create_index("ix_signal_evidence_nodes_epistemic_type", "signal_evidence_nodes", ["epistemic_type"])
    op.create_index("ix_signal_evidence_nodes_signal_type", "signal_evidence_nodes", ["signal_type"])


def downgrade() -> None:
    op.drop_index("ix_signal_evidence_nodes_signal_type", table_name="signal_evidence_nodes")
    op.drop_index("ix_signal_evidence_nodes_epistemic_type", table_name="signal_evidence_nodes")
    op.drop_index("ix_signal_evidence_nodes_company_id", table_name="signal_evidence_nodes")
    op.drop_index("ix_signal_evidence_nodes_id", table_name="signal_evidence_nodes")
    op.drop_table("signal_evidence_nodes")

    op.drop_index("ix_company_belief_states_company_id", table_name="company_belief_states")
    op.drop_index("ix_company_belief_states_id", table_name="company_belief_states")
    op.drop_table("company_belief_states")
