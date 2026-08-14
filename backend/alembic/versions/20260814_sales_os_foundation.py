"""Neutralized non-canonical Sales OS migration (syntax fix)

Preserves original revision metadata but no-op upgrade/downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260814_sales_os"
down_revision: Union[str, None] = "9073563ba3cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Neutralized migration: original schema is created by the canonical migration.
    This function intentionally does nothing to avoid duplicate CREATE TABLE on fresh DBs.
    """
    pass


def downgrade() -> None:
    """Conservative no-op downgrade for the neutralized migration."""
    pass
