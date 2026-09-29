from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from eklabs_platform.core.db.base import Base
from eklabs_platform.core.db.mixins import TenantScopedMixin, UUIDPkMixin

# Provisional — matches the parsers spec §1 names (PyMuPDF, Docling, pandas,
# LibreOffice). Extend with a new migration as new source formats are ingested;
# CHECK, not a native enum, is exactly so that extension is a one-line change.
FILE_TYPES = ("pdf", "docx", "doc", "xlsx", "xls", "rtf", "xml", "other")
STATUSES = ("uploaded", "queued", "parsing", "parsed", "failed")


class Document(Base, UUIDPkMixin, TenantScopedMixin):
    """Any source file — spec §4. `status` is the one field legitimately
    mutated in place (pipeline state); every transition is also written to
    audit_log via record_event(), which is what gives the audit trail here."""

    __tablename__ = "document"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        UniqueConstraint("tenant_id", "s3_key"),
        # Composite-FK target for page.document_id / chunk.document_id.
        UniqueConstraint("id", "tenant_id"),
        Index("ix_document_tenant_id_sha256", "tenant_id", "sha256"),
        CheckConstraint(
            "file_type IN (" + ", ".join(f"'{t}'" for t in FILE_TYPES) + ")",
            name="file_type_valid",
        ),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in STATUSES) + ")",
            name="status_valid",
        ),
    )

    title: Mapped[str] = mapped_column(nullable=False)
    file_type: Mapped[str] = mapped_column(nullable=False)
    s3_key: Mapped[str] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False, server_default="uploaded")
    # Where it came from; 'upload' if manual (spec §4).
    source_system: Mapped[str] = mapped_column(nullable=False, server_default="upload")
    source_id: Mapped[str | None]
    source_version: Mapped[str | None]
    source_url: Mapped[str | None]
    synced_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
