"""Merge Alembic heads into a single linear head.

Revision ID: merge_heads_2026
Revises: 20260814_sales_os, c8d3e5f70124, d2e3f4a5b6c7
"""
from typing import Sequence, Union
from alembic import op

revision: str = "merge_heads_2026"
down_revision: Union[str, Sequence[str], None] = (
    "20260814_sales_os",
    "c8d3e5f70124",
    "d2e3f4a5b6c7",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
