"""create knowledge base tables

Revision ID: 5fa2c3d7e901
Revises: 9b21d4a6c1f2
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "5fa2c3d7e901"
down_revision = "9b21d4a6c1f2"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("knowledge_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("document_type", sa.String(100), server_default="internal"),
        sa.Column("company", sa.String(500)),
        sa.Column("source_uri", sa.String(1000)),
        sa.Column("source_name", sa.String(500)),
        sa.Column("document_date", sa.Date()),
        sa.Column("version", sa.String(100)),
        sa.Column("content_hash", sa.String(128), unique=True),
        sa.Column("status", sa.String(50), server_default="active"),
        sa.Column("metadata_json", JSONB),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_documents_title", "knowledge_documents", ["title"])
    op.create_index("ix_knowledge_documents_document_type", "knowledge_documents", ["document_type"])
    op.create_index("ix_knowledge_documents_status", "knowledge_documents", ["status"])
    op.create_table("knowledge_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("section", sa.String(500)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("fact_classification", sa.String(50), server_default="VERIFIED_FACT"),
        sa.Column("source_reference", sa.String(1000)),
        sa.Column("source_date", sa.Date()),
        sa.Column("confidence", sa.Integer(), server_default="100"),
        sa.Column("embedding_model", sa.String(200)),
        sa.Column("metadata_json", JSONB),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])
    op.create_index("ix_knowledge_chunks_fact_classification", "knowledge_chunks", ["fact_classification"])

def downgrade():
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
