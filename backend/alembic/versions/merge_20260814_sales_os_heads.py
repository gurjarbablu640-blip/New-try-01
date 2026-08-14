"""Merge multiple Sales OS migration heads into a single head.

Revision ID: merge_20260814_heads
Revises: 20260814_sales_os, 9b21d4a6c1f2, c8d3e5f70124, d2e3f4a5b6c7
"""
from alembic import op
import sqlalchemy as sa

revision = "merge_20260814_heads"
down_revision = (
    "add_missing_salesos_idx",
    "merge_competitor_20260814",
)
branch_labels = None
depends_on = None


def upgrade():
    # Empty merge migration: unify Alembic heads. Schema reconciliation is handled
    # by canonical migrations. Do not perform schema operations here.
    pass


def downgrade():
    # Downgrade for a merge is not supported because history rewriting would be
    # required to separate the branches. Leave conservative.
    raise NotImplementedError("Downgrade of merge migration is not supported.")
