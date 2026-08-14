"""Merge non-canonical and canonical Sales OS migrations into a single Sales OS merge.

Revision ID: merge_salesos_20260814
Revises: 20260814_sales_os, 9b21d4a6c1f2
"""
from alembic import op
import sqlalchemy as sa

revision = "merge_salesos_20260814"
down_revision = (
    "20260814_sales_os",
    "9b21d4a6c1f2",
)
branch_labels = None
depends_on = None


def upgrade():
    # Empty staged merge for Sales OS duplicates. No schema operations.
    pass


def downgrade():
    # Conservative: do not attempt to split merged history.
    raise NotImplementedError("Downgrade of staged Sales OS merge is not supported.")
