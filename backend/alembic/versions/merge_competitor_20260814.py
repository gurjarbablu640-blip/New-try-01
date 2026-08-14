"""Merge non-canonical and canonical Competitor migrations into a single competitor merge.

Revision ID: merge_competitor_20260814
Revises: c8d3e5f70124, d2e3f4a5b6c7
"""
from alembic import op
import sqlalchemy as sa

revision = "merge_competitor_20260814"
down_revision = (
    "c8d3e5f70124",
    "d2e3f4a5b6c7",
)
branch_labels = None
depends_on = None


def upgrade():
    # Empty staged merge for competitor duplicates. No schema operations.
    pass


def downgrade():
    raise NotImplementedError("Downgrade of staged competitor merge is not supported.")
