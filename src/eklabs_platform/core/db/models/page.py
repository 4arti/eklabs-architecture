import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from eklabs_platform.core.db.base import Base
from eklabs_platform.core.db.mixins import TenantScopedMixin, UUIDPkMixin


class Page(Base, UUIDPkMixin, TenantScopedMixin):
    """One rendered page of a document. Immutable — a re-parse creates a new
    document row, never an in-place edit of an existing page."""

    __tablename__ = "page"
    __table_args__ = (
        # Composite FK: a page can only belong to a document owned by the
        # SAME tenant it itself claims — a mismatched tenant_id/document_id
        # pair is a foreign-key violation, not just something RLS filters.
        ForeignKeyConstraint(["document_id", "tenant_id"], ["document.id", "document.tenant_id"]),
        UniqueConstraint("document_id", "page_no"),
        CheckConstraint(
            "ocr_confidence IS NULL OR ocr_confidence BETWEEN 0 AND 1", name="ocr_confidence_range"
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    page_no: Mapped[int] = mapped_column(nullable=False)
    ocr_confidence: Mapped[float | None]
    render_s3_key: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
