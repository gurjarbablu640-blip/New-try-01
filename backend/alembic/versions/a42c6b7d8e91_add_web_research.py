"""Add web research evidence table."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a42c6b7d8e91"
down_revision: Union[str, None] = "9b21d4a6c1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "web_research",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("title", sa.String(1000)),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_domain", sa.String(300)),
        sa.Column("published_date", sa.DateTime()),
        sa.Column("retrieved_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("snippet", sa.Text()),
        sa.Column("content", sa.Text()),
        sa.Column("signal_type", sa.String(100)),
        sa.Column("confidence", sa.Integer(), server_default="50"),
        sa.Column("evidence_type", sa.String(50), server_default="WEB_EVIDENCE"),
        sa.Column("metadata_json", JSONB),
    )
    op.create_index("ix_web_research_company_id", "web_research", ["company_id"])
    op.create_index("ix_web_research_source_domain", "web_research", ["source_domain"])
    op.create_index("ix_web_research_signal_type", "web_research", ["signal_type"])
    op.create_index("ix_web_research_retrieved_at", "web_research", ["retrieved_at"])


def downgrade() -> None:
    op.drop_table("web_research")
