"""Create competitor intelligence tables.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "competitor_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(500), nullable=False, unique=True),
        sa.Column("website", sa.String(1000)),
        sa.Column("country", sa.String(100)),
        sa.Column("service_focus", sa.Text()),
        sa.Column("positioning", sa.Text()),
        sa.Column("pricing_notes", sa.Text()),
        sa.Column("strengths", JSONB),
        sa.Column("weaknesses", JSONB),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata_json", JSONB),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_competitor_profiles_name", "competitor_profiles", ["name"])
    op.create_index("ix_competitor_profiles_active", "competitor_profiles", ["active"])

    op.create_table(
        "competitor_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("competitor_id", sa.Integer(), sa.ForeignKey("competitor_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="SET NULL")),
        sa.Column("observation_type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("source_name", sa.String(500)),
        sa.Column("observed_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("confidence", sa.Integer(), server_default="50"),
        sa.Column("classification", sa.String(50), server_default="WEB_EVIDENCE"),
        sa.Column("metadata_json", JSONB),
    )
    op.create_index("ix_competitor_observations_competitor_id", "competitor_observations", ["competitor_id"])
    op.create_index("ix_competitor_observations_company_id", "competitor_observations", ["company_id"])
    op.create_index("ix_competitor_observations_observation_type", "competitor_observations", ["observation_type"])


def downgrade():
    op.drop_table("competitor_observations")
    op.drop_table("competitor_profiles")
