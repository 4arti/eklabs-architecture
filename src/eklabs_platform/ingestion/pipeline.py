"""The plain, arq-agnostic orchestrator: parse -> chunk -> embed -> record.
No `arq` import here at all — `ingestion/jobs.py` is a thin wrapper around
this, and tests call `ingest_document()` directly with a real session, no
background worker needed to prove the pipeline works.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from eklabs_platform.core.db.models.document import Document
from eklabs_platform.core.documents import transition_status
from eklabs_platform.core.storage import download_bytes
from eklabs_platform.ingestion.chunking import chunk_document
from eklabs_platform.ingestion.parsing import parse_document
from eklabs_platform.ingestion.record import IngestResult, record_parsed_document
from eklabs_platform.knowledge.embedding import embed_passages


async def ingest_document(
    session: AsyncSession, *, tenant_id: uuid.UUID, actor: uuid.UUID, document_id: uuid.UUID
) -> IngestResult:
    """Drives `document.status` through uploaded -> parsing -> parsed/failed,
    each transition going through the existing `record_event()` via
    `transition_status()` — document.py's own docstring already promises
    this; this is wiring it up for real, not new audit machinery."""
    document = await session.get_one(Document, document_id)

    await transition_status(
        session, tenant_id=tenant_id, actor=actor, document_id=document_id, status="parsing"
    )

    try:
        file_bytes = await download_bytes(document.s3_key)
        parsed = await parse_document(document.title, file_bytes)
        chunks = await chunk_document(parsed.docling_doc)
        embeddings = await embed_passages([chunk.text for chunk in chunks])
        result = await record_parsed_document(
            session,
            tenant_id=tenant_id,
            document_id=document_id,
            parsed=parsed,
            chunks=chunks,
            chunk_embeddings=embeddings,
        )
    except Exception:
        await transition_status(
            session, tenant_id=tenant_id, actor=actor, document_id=document_id, status="failed"
        )
        raise

    await transition_status(
        session, tenant_id=tenant_id, actor=actor, document_id=document_id, status="parsed"
    )
    return result
