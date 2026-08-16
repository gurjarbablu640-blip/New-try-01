"""Add Oorja Sales OS foundation tables (historical no-op revision).

Revision ID: 20260814_sales_os
Revises: 9073563ba3cc
"""
from typing import Sequence, Union
from alembic import op

revision: str = "20260814_sales_os"
down_revision: Union[str, None] = "9073563ba3cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
