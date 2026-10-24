import hashlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from eklabs_platform.core.db.audit import record_event
from eklabs_platform.core.db.models.document import FILE_TYPES, STATUSES, Document
from eklabs_platform.core.storage import upload_bytes

_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "rtf": "application/rtf",
    "xml": "application/xml",
    "other": "application/octet-stream",
}


async def register_document(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: uuid.UUID,
    title: str,
    file_type: str,
    file_bytes: bytes,
    source_system: str = "upload",
    source_id: str | None = None,
    source_version: str | None = None,
    source_url: str | None = None,
) -> Document:
    """The one sanctioned writer for new `document` rows — mirrors
    `record_event()`/`create_application()`. Uploads to storage before
    touching the database, so a failed upload never leaves a document row
    pointing at a file that doesn't exist; a failed insert after a
    successful upload just leaves one orphaned object, the same class of
    imperfection already accepted elsewhere in this codebase (no two-phase
    commit between Postgres and S3).

    `document_id` is generated client-side, not left to the server default,
    so the S3 key can be built before the row exists — not an RLS/RETURNING
    concern like `make_tenant()`'s fix (the caller is already inside a
    `tenant_scoped_session(tenant_id)` matching this row's own tenant_id).
    """
    if file_type not in FILE_TYPES:
        raise ValueError(f"{file_type!r} is not a recognized file_type: {FILE_TYPES!r}")

    document_id = uuid.uuid4()
    sha256 = hashlib.sha256(file_bytes).hexdigest()
    # Tenant-prefixed key — spec §13: "files under per-client S3 prefixes" —
    # enforced at the storage layer too, not just by Postgres RLS.
    s3_key = f"{tenant_id}/{document_id}.{file_type}"

    await upload_bytes(s3_key, file_bytes, content_type=_CONTENT_TYPES[file_type])

    document = Document(
        id=document_id,
        tenant_id=tenant_id,
        title=title,
        file_type=file_type,
        s3_key=s3_key,
        sha256=sha256,
        source_system=source_system,
        source_id=source_id,
        source_version=source_version,
        source_url=source_url,
    )
    session.add(document)
    await session.flush()

    await record_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action="document.created",
        target_table="document",
        target_id=document.id,
        after={"title": title, "file_type": file_type, "s3_key": s3_key, "sha256": sha256},
    )
    return document


async def transition_status(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: uuid.UUID,
    document_id: uuid.UUID,
    status: str,
) -> None:
    """The one sanctioned way to move `document.status` — fulfils the
    model's own docstring promise ("every transition is also written to
    audit_log via record_event()"). `status` is the one field legitimately
    mutated in place (document.py's docstring); everything else about a
    document is immutable."""
    if status not in STATUSES:
        raise ValueError(f"{status!r} is not a recognized status: {STATUSES!r}")

    # PK-only lookup — Document's primary key is just `id`; RLS (the
    # session is already scoped to tenant_id) is what makes this
    # tenant-safe, not an extra filter here.
    document = await session.get_one(Document, document_id)
    before_status = document.status
    document.status = status
    await session.flush()

    await record_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action="document.status_changed",
        target_table="document",
        target_id=document_id,
        before={"status": before_status},
        after={"status": status},
    )
