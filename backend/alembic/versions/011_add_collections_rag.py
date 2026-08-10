"""add collections rag"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "011_collections_rag"
down_revision: Union[str, None] = "010_message_api_cost"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table("collections", sa.Column("id", sa.UUID(), primary_key=True), sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(255), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("tenant_id", "name", name="uq_collections_tenant_name"))
    op.create_index("ix_collections_tenant_id", "collections", ["tenant_id"])
    op.create_table("agent_collections", sa.Column("agent_id", sa.UUID(), sa.ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True), sa.Column("collection_id", sa.UUID(), sa.ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True))
    op.create_table("collection_documents", sa.Column("id", sa.UUID(), primary_key=True), sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False), sa.Column("collection_id", sa.UUID(), sa.ForeignKey("collections.id", ondelete="CASCADE"), nullable=False), sa.Column("original_name", sa.String(255), nullable=False), sa.Column("content_type", sa.String(100), nullable=False), sa.Column("size_bytes", sa.BigInteger(), nullable=False), sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_collection_documents_tenant_id", "collection_documents", ["tenant_id"])
    op.create_index("ix_collection_documents_collection_id", "collection_documents", ["collection_id"])
    op.create_table("document_chunks", sa.Column("id", sa.UUID(), primary_key=True), sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False), sa.Column("collection_id", sa.UUID(), sa.ForeignKey("collections.id", ondelete="CASCADE"), nullable=False), sa.Column("document_id", sa.UUID(), sa.ForeignKey("collection_documents.id", ondelete="CASCADE"), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.Column("page_number", sa.Integer()), sa.Column("content", sa.Text(), nullable=False), sa.Column("embedding", Vector(1536), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_document_chunks_tenant_id", "document_chunks", ["tenant_id"])
    op.create_index("ix_document_chunks_collection_id", "document_chunks", ["collection_id"])
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.execute("CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops)")

def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_table("collection_documents")
    op.drop_table("agent_collections")
    op.drop_table("collections")
