import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from eklabs_platform.core.db.models.chunk import Chunk
from eklabs_platform.core.db.models.page import Page
from eklabs_platform.core.db.models.table_extract import TableExtract
from eklabs_platform.ingestion.chunking import ChunkData
from eklabs_platform.ingestion.parsing import ParsedDocument


class IngestResult:
    def __init__(self, page_count: int, table_count: int, chunk_count: int) -> None:
        self.page_count = page_count
        self.table_count = table_count
        self.chunk_count = chunk_count


async def record_parsed_document(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    parsed: ParsedDocument,
    chunks: list[ChunkData],
    chunk_embeddings: list[list[float]],
) -> IngestResult:
    """The one sanctioned writer for page/table_extract/chunk rows together
    — mirrors record_event()/create_application()/register_document().
    One Docling conversion produces all three in lockstep, so they're
    inserted as one invariant-checked unit (same transaction, same
    function) rather than three writers a caller could invoke out of order
    or partially."""
    if len(chunks) != len(chunk_embeddings):
        raise ValueError(
            f"{len(chunks)} chunks but {len(chunk_embeddings)} embeddings — caller must embed "
            "every chunk before recording."
        )

    for page in parsed.pages:
        session.add(
            Page(
                tenant_id=tenant_id,
                document_id=document_id,
                page_no=page.page_no,
                ocr_confidence=page.ocr_confidence,
            )
        )

    for table in parsed.tables:
        session.add(
            TableExtract(
                tenant_id=tenant_id,
                document_id=document_id,
                page_no=table.page_no,
                cells=table.cells,
            )
        )

    for chunk, embedding in zip(chunks, chunk_embeddings, strict=True):
        session.add(
            Chunk(
                tenant_id=tenant_id,
                document_id=document_id,
                section_path=chunk.section_path,
                text=chunk.text,
                page=chunk.page,
                bbox=chunk.bbox,
                embedding=embedding,
            )
        )

    await session.flush()
    return IngestResult(
        page_count=len(parsed.pages), table_count=len(parsed.tables), chunk_count=len(chunks)
    )
