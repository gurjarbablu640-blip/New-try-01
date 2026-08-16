"""Step 1: Add lead engine, deduplication, email validation, and qualification fields.

Revision ID: 20260817_step1_lead_engine
Revises: add_salesos_perf_idx_2026
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260817_step1_lead_engine"
down_revision: Union[str, None] = "add_salesos_perf_idx_2026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Company fields
    op.add_column("companies", sa.Column("normalized_name", sa.String(length=500), nullable=True))
    op.add_column("companies", sa.Column("domain", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("source", sa.String(length=100), server_default="manual", nullable=True))
    op.add_column("companies", sa.Column("apollo_id", sa.String(length=100), nullable=True))
    op.add_column("companies", sa.Column("qualification_status", sa.String(length=50), server_default="RAW", nullable=True))
    op.add_column("companies", sa.Column("qualification_reason", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("qualified_at", sa.DateTime(), nullable=True))

    op.create_index("ix_companies_normalized_name", "companies", ["normalized_name"])
    op.create_index("ix_companies_domain", "companies", ["domain"])
    op.create_index("ix_companies_source", "companies", ["source"])
    op.create_index("ix_companies_apollo_id", "companies", ["apollo_id"])
    op.create_index("ix_companies_qualification_status", "companies", ["qualification_status"])

    # Person fields
    op.add_column("persons", sa.Column("normalized_email", sa.String(length=300), nullable=True))
    op.add_column("persons", sa.Column("normalized_phone", sa.String(length=50), nullable=True))
    op.add_column("persons", sa.Column("apollo_id", sa.String(length=100), nullable=True))
    op.add_column("persons", sa.Column("email_verification_status", sa.String(length=50), server_default="unverified", nullable=True))
    op.add_column("persons", sa.Column("email_verification_reason", sa.String(length=200), nullable=True))
    op.add_column("persons", sa.Column("email_verified_at", sa.DateTime(), nullable=True))

    op.create_index("ix_persons_normalized_email", "persons", ["normalized_email"])
    op.create_index("ix_persons_normalized_phone", "persons", ["normalized_phone"])
    op.create_index("ix_persons_apollo_id", "persons", ["apollo_id"])
    op.create_index("ix_persons_email_verification_status", "persons", ["email_verification_status"])


def downgrade() -> None:
    op.drop_index("ix_persons_email_verification_status", table_name="persons")
    op.drop_index("ix_persons_apollo_id", table_name="persons")
    op.drop_index("ix_persons_normalized_phone", table_name="persons")
    op.drop_index("ix_persons_normalized_email", table_name="persons")

    op.drop_column("persons", "email_verified_at")
    op.drop_column("persons", "email_verification_reason")
    op.drop_column("persons", "email_verification_status")
    op.drop_column("persons", "apollo_id")
    op.drop_column("persons", "normalized_phone")
    op.drop_column("persons", "normalized_email")

    op.drop_index("ix_companies_qualification_status", table_name="companies")
    op.drop_index("ix_companies_apollo_id", table_name="companies")
    op.drop_index("ix_companies_source", table_name="companies")
    op.drop_index("ix_companies_domain", table_name="companies")
    op.drop_index("ix_companies_normalized_name", table_name="companies")

    op.drop_column("companies", "qualified_at")
    op.drop_column("companies", "qualification_reason")
    op.drop_column("companies", "qualification_status")
    op.drop_column("companies", "apollo_id")
    op.drop_column("companies", "source")
    op.drop_column("companies", "domain")
    op.drop_column("companies", "normalized_name")
