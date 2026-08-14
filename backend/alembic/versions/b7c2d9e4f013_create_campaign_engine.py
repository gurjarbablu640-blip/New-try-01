"""Create controlled campaign engine tables.

Revision ID: b7c2d9e4f013
Revises: a42c6b7d8e91
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "b7c2d9e4f013"
down_revision = "a42c6b7d8e91"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("channel", sa.String(50), nullable=False, server_default="email"),
        sa.Column("status", sa.String(50), nullable=False, server_default="Draft"),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("segment_filters", JSONB),
        sa.Column("daily_limit", sa.Integer(), server_default="50"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_campaigns_status", "campaigns", ["status"])

    op.create_table(
        "campaign_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False, server_default="email"),
        sa.Column("delay_days", sa.Integer(), server_default="0"),
        sa.Column("subject", sa.String(1000)),
        sa.Column("body_template", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.create_table(
        "campaign_recipients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id", ondelete="SET NULL")),
        sa.Column("current_step", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="Queued"),
        sa.Column("email_status", sa.String(50), server_default="Pending"),
        sa.Column("last_sent_at", sa.DateTime()),
        sa.Column("next_send_at", sa.DateTime()),
        sa.Column("replied_at", sa.DateTime()),
        sa.Column("bounced_at", sa.DateTime()),
        sa.Column("metadata_json", JSONB),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_campaign_recipients_status", "campaign_recipients", ["status"])

    op.create_table(
        "campaign_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("campaign_recipients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("channel", sa.String(50)),
        sa.Column("provider_message_id", sa.String(500)),
        sa.Column("payload", JSONB),
        sa.Column("occurred_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_campaign_events_event_type", "campaign_events", ["event_type"])


def downgrade():
    op.drop_table("campaign_events")
    op.drop_table("campaign_recipients")
    op.drop_table("campaign_steps")
    op.drop_table("campaigns")
