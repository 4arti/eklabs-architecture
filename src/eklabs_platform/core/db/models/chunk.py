import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKeyConstraint, Index, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from eklabs_platform.core.db.base import Base
from eklabs_platform.core.db.mixins import TenantScopedMixin, UUIDPkMixin

# Voyage AI's current default embedding dimension (spec §1). Placeholder to
# confirm with whoever wires platform/llm — pgvector columns are fixed-width,
# so changing this later is a new migration, not a config change.
EMBEDDING_DIM = 1024


class Chunk(Base, UUIDPkMixin, TenantScopedMixin):
    """A retrievable slice of a document's text, with its embedding."""

    __tablename__ = "chunk"
    __table_args__ = (
        ForeignKeyConstraint(["document_id", "tenant_id"], ["document.id", "document.tenant_id"]),
        Index("ix_chunk_document_id_page", "document_id", "page"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    section_path: Mapped[str | None]
    text: Mapped[str] = mapped_column(nullable=False)
    # Plain int, not FK'd to page.page_no — a chunk can span or precede page
    # rendering, so a hard link to a specific page row would be wrong in
    # general.
    page: Mapped[int | None]
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
