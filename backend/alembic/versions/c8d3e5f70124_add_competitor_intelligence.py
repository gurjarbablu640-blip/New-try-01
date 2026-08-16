"""Add competitor intelligence tables (historical no-op revision).

Revision ID: c8d3e5f70124
Revises: b7c2d9e4f013
"""
from typing import Sequence, Union
from alembic import op

revision: str = "c8d3e5f70124"
down_revision: Union[str, None] = "b7c2d9e4f013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
