import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKeyConstraint, Index, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from eklabs_platform.core.db.base import Base
from eklabs_platform.core.db.mixins import TenantScopedMixin, UUIDPkMixin


class TableExtract(Base, UUIDPkMixin, TenantScopedMixin):
    """An exact table grid pulled from a source page — spec §4/§6. Kept
    separate from `chunk` because a table is never split mid-row for search;
    `cells` preserves row/col spans, not a flattened text blob."""

    __tablename__ = "table_extract"
    __table_args__ = (
        # Same composite-FK shape as page/chunk: a table_extract can only
        # belong to a document owned by the SAME tenant it claims.
        ForeignKeyConstraint(["document_id", "tenant_id"], ["document.id", "document.tenant_id"]),
        Index("ix_table_extract_document_id_page_no", "document_id", "page_no"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    page_no: Mapped[int] = mapped_column(nullable=False)
    cells: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
