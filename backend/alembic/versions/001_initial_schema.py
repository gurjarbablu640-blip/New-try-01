"""Initial schema — all modules 8-17

Revision ID: 001_initial
Revises: None
Create Date: 2025-05-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ---- companies ----
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(500), nullable=False, index=True),
        sa.Column("city", sa.String(200)),
        sa.Column("state", sa.String(200)),
        sa.Column("country", sa.String(100), server_default="India"),
        sa.Column("industry", sa.String(300)),
        sa.Column("search_keyword", sa.String(300)),
        sa.Column("website", sa.String(500)),
        sa.Column("phone", sa.String(100)),
        sa.Column("email", sa.String(300)),
        sa.Column("icp_score", sa.Float, server_default="0"),
        sa.Column("intent_velocity_score", sa.Float, server_default="0"),
        sa.Column("calculated_tier", sa.String(100), server_default="Unscored"),
        sa.Column("headcount_bracket", sa.String(50)),
        sa.Column("has_nabl", sa.Boolean, server_default="false"),
        sa.Column("nabl_first_seen", sa.DateTime),
        sa.Column("predicted_renewal_date", sa.DateTime),
        sa.Column("buying_window", sa.Text, server_default="unknown"),
        sa.Column("urgency_reason", sa.Text),
        sa.Column("competitor_pain_detected", sa.Boolean, server_default="false"),
        sa.Column("review_sentiment_score", sa.Float),
        sa.Column("lookalike_source_id", sa.Integer),
        sa.Column("user_rating", sa.Integer),
        sa.Column("negative_icp_flags", ARRAY(sa.Text), server_default="{}"),
        sa.Column("export_active", sa.Boolean, server_default="false"),
        sa.Column("google_place_id", sa.String(300)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_companies_icp_score", "companies", [sa.text("icp_score DESC")])
    op.create_index("idx_companies_tier", "companies", ["calculated_tier"])
    op.create_index("idx_companies_buying_window", "companies", ["buying_window"])

    # Add vector column separately (alembic doesn't natively handle pgvector)
    op.execute("ALTER TABLE companies ADD COLUMN name_embedding vector(768)")

    # Self-referencing FK for lookalike
    op.create_foreign_key(
        "fk_companies_lookalike",
        "companies", "companies",
        ["lookalike_source_id"], ["id"],
    )

    # ---- persons ----
    op.create_table(
        "persons",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("full_name", sa.String(300)),
        sa.Column("designation", sa.String(300)),
        sa.Column("email", sa.String(300)),
        sa.Column("phone", sa.String(100)),
        sa.Column("linkedin_url", sa.String(500)),
        sa.Column("seniority_level", sa.String(100)),
        sa.Column("department", sa.String(200)),
        sa.Column("is_decision_maker", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ---- company_website_intel ----
    op.create_table(
        "company_website_intel",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("instruments_found", ARRAY(sa.Text), server_default="{}"),
        sa.Column("oem_brands", ARRAY(sa.Text), server_default="{}"),
        sa.Column("iso_standards", ARRAY(sa.Text), server_default="{}"),
        sa.Column("certifications_expiry_hints", sa.Text),
        sa.Column("expansion_signals", sa.Text),
        sa.Column("services_offered", ARRAY(sa.Text), server_default="{}"),
        sa.Column("industries_served", ARRAY(sa.Text), server_default="{}"),
        sa.Column("competitor_mentions", ARRAY(sa.Text), server_default="{}"),
        sa.Column("review_pain_phrases", ARRAY(sa.Text), server_default="{}"),
        sa.Column("last_crawled_at", sa.DateTime),
        sa.Column("crawl_status", sa.String(50), server_default="pending"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ---- company_intent_signals ----
    op.create_table(
        "company_intent_signals",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("signal_type", sa.String(100), nullable=False, index=True),
        sa.Column("weight_applied", sa.Float, server_default="0"),
        sa.Column("source_url", sa.Text),
        sa.Column("source_snippet", sa.Text),
        sa.Column("urgency_reason", sa.Text),
        sa.Column("opportunity_note", sa.Text),
        sa.Column("detected_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime),
        sa.Column("is_active", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_signals_active", "company_intent_signals", ["is_active"])

    # ---- outreach_drafts ----
    op.create_table(
        "outreach_drafts",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email_subject", sa.Text),
        sa.Column("email_body", sa.Text),
        sa.Column("whatsapp_message", sa.Text),
        sa.Column("email_subject_variants", ARRAY(sa.Text), server_default="{}"),
        sa.Column("email_ps", sa.Text),
        sa.Column("call_opener", sa.Text),
        sa.Column("objection_responses", JSONB),
        sa.Column("free_value_offer_outline", sa.Text),
        sa.Column("linkedin_connection_note", sa.Text),
        sa.Column("followup_day3_whatsapp", sa.Text),
        sa.Column("followup_day7_email", sa.Text),
        sa.Column("followup_day14_breakup", sa.Text),
        sa.Column("generated_by", sa.String(100), server_default="claude"),
        sa.Column("generation_context", JSONB),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ---- pipeline_stages ----
    op.create_table(
        "pipeline_stages",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("person_id", sa.Integer, sa.ForeignKey("persons.id")),
        sa.Column("stage", sa.Text, server_default="New", index=True),
        sa.Column("contact_channel", sa.Text),
        sa.Column("next_action", sa.Text),
        sa.Column("next_action_date", sa.Date),
        sa.Column("deal_value_est", sa.Numeric),
        sa.Column("loss_reason", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("last_touched", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_pipeline_next_action_date", "pipeline_stages", ["next_action_date"])

    # ---- activities ----
    op.create_table(
        "activities",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("person_id", sa.Integer, sa.ForeignKey("persons.id")),
        sa.Column("pipeline_id", sa.Integer, sa.ForeignKey("pipeline_stages.id")),
        sa.Column("activity_type", sa.Text, nullable=False),
        sa.Column("outcome", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("occurred_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ---- ab_test_results ----
    op.create_table(
        "ab_test_results",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("subject_variant", sa.Integer),
        sa.Column("opened", sa.Boolean, server_default="false"),
        sa.Column("replied", sa.Boolean, server_default="false"),
        sa.Column("sent_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ---- lead_ratings ----
    op.create_table(
        "lead_ratings",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("user_rating", sa.Integer, nullable=False),
        sa.Column("rating_reason", sa.Text),
        sa.Column("rated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ---- won_customers ----
    op.create_table(
        "won_customers",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_vector", JSONB),
        sa.Column("won_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("won_customers")
    op.drop_table("lead_ratings")
    op.drop_table("ab_test_results")
    op.drop_table("activities")
    op.drop_table("pipeline_stages")
    op.drop_table("outreach_drafts")
    op.drop_table("company_intent_signals")
    op.drop_table("company_website_intel")
    op.drop_table("persons")
    op.drop_table("companies")
    op.execute("DROP EXTENSION IF EXISTS vector")
