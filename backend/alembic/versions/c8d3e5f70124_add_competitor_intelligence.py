"""Add competitor intelligence tables.

Revision ID: c8d3e5f70124
Revises: b7c2d9e4f013
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "c8d3e5f70124"
down_revision = "b7c2d9e4f013"
branch_labels = None
depends_on = None


def upgrade():
    # Neutralized duplicate migration: the canonical migration d2e3f4a5b6c7 is the correct creator
    # of the competitor tables. This upgrade is intentionally a no-op to avoid duplicate
    # CREATE TABLE attempts on fresh databases when the canonical migration also runs.
    return

    
    
    
    
    
    
    



def downgrade():
    # Conservative downgrade: do not drop tables created by the canonical migration.
    # This downgrade intentionally avoids destructive operations.
    return
