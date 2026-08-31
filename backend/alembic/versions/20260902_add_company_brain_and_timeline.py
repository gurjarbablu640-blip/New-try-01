"""Add Company Brain, Timeline, Stakeholder Graph, and Regulatory Intelligence tables.

Revision ID: 20260902_company_brain
Revises: 20260901_conv_memory
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260902_company_brain"
down_revision: Union[str, None] = "20260901_conv_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. company_intelligence_facts
    op.create_table(
        "company_intelligence_facts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("fact_key", sa.String(length=100), nullable=False),
        sa.Column("fact_value", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="0.8", nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("verified_by_human", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_company_intelligence_facts_id", "company_intelligence_facts", ["id"])
    op.create_index("ix_company_intelligence_facts_company_id", "company_intelligence_facts", ["company_id"])
    op.create_index("ix_company_intelligence_facts_category", "company_intelligence_facts", ["category"])
    op.create_index("ix_company_intelligence_facts_fact_key", "company_intelligence_facts", ["fact_key"])

    # 2. company_timeline_events
    op.create_table(
        "company_timeline_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("impact_level", sa.String(length=20), server_default="medium", nullable=False),
        sa.Column("buying_window_impact", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("raw_metadata", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_company_timeline_events_id", "company_timeline_events", ["id"])
    op.create_index("ix_company_timeline_events_company_id", "company_timeline_events", ["company_id"])
    op.create_index("ix_company_timeline_events_event_type", "company_timeline_events", ["event_type"])
    op.create_index("ix_company_timeline_events_event_date", "company_timeline_events", ["event_date"])

    # 3. stakeholder_intelligence
    op.create_table(
        "stakeholder_intelligence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stakeholder_role", sa.String(length=50), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=False),
        sa.Column("incentive_focus", sa.String(length=100), nullable=True),
        sa.Column("influence_weight", sa.Float(), server_default="5.0", nullable=False),
        sa.Column("engagement_status", sa.String(length=50), server_default="unreached", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_stakeholder_intelligence_id", "stakeholder_intelligence", ["id"])
    op.create_index("ix_stakeholder_intelligence_company_id", "stakeholder_intelligence", ["company_id"])
    op.create_index("ix_stakeholder_intelligence_person_id", "stakeholder_intelligence", ["person_id"])
    op.create_index("ix_stakeholder_intelligence_stakeholder_role", "stakeholder_intelligence", ["stakeholder_role"])
    op.create_index("ix_stakeholder_intelligence_department", "stakeholder_intelligence", ["department"])

    # 4. regulatory_intelligence
    op.create_table(
        "regulatory_intelligence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("authority", sa.String(length=100), nullable=False),
        sa.Column("regulation_code", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("affected_industries", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("affected_parameters", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("affected_equipment", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("compliance_deadline", sa.Date(), nullable=True),
        sa.Column("commercial_impact_analysis", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_regulatory_intelligence_id", "regulatory_intelligence", ["id"])
    op.create_index("ix_regulatory_intelligence_authority", "regulatory_intelligence", ["authority"])
    op.create_index("ix_regulatory_intelligence_regulation_code", "regulatory_intelligence", ["regulation_code"])
    op.create_index("ix_regulatory_intelligence_compliance_deadline", "regulatory_intelligence", ["compliance_deadline"])


def downgrade() -> None:
    op.drop_index("ix_regulatory_intelligence_compliance_deadline", table_name="regulatory_intelligence")
    op.drop_index("ix_regulatory_intelligence_regulation_code", table_name="regulatory_intelligence")
    op.drop_index("ix_regulatory_intelligence_authority", table_name="regulatory_intelligence")
    op.drop_index("ix_regulatory_intelligence_id", table_name="regulatory_intelligence")
    op.drop_table("regulatory_intelligence")

    op.drop_index("ix_stakeholder_intelligence_department", table_name="stakeholder_intelligence")
    op.drop_index("ix_stakeholder_intelligence_stakeholder_role", table_name="stakeholder_intelligence")
    op.drop_index("ix_stakeholder_intelligence_person_id", table_name="stakeholder_intelligence")
    op.drop_index("ix_stakeholder_intelligence_company_id", table_name="stakeholder_intelligence")
    op.drop_index("ix_stakeholder_intelligence_id", table_name="stakeholder_intelligence")
    op.drop_table("stakeholder_intelligence")

    op.drop_index("ix_company_timeline_events_event_date", table_name="company_timeline_events")
    op.drop_index("ix_company_timeline_events_event_type", table_name="company_timeline_events")
    op.drop_index("ix_company_timeline_events_company_id", table_name="company_timeline_events")
    op.drop_index("ix_company_timeline_events_id", table_name="company_timeline_events")
    op.drop_table("company_timeline_events")

    op.drop_index("ix_company_intelligence_facts_fact_key", table_name="company_intelligence_facts")
    op.drop_index("ix_company_intelligence_facts_category", table_name="company_intelligence_facts")
    op.drop_index("ix_company_intelligence_facts_company_id", table_name="company_intelligence_facts")
    op.drop_index("ix_company_intelligence_facts_id", table_name="company_intelligence_facts")
    op.drop_table("company_intelligence_facts")
