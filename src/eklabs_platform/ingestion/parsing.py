"""Docling wrapper — the only file in this codebase that imports `docling`.
Docling covers native PDF text, OCR for scans, table structure extraction,
and Word parsing in one tool (spec §1 originally split this three ways
across PyMuPDF/Azure Document Intelligence/Docling; this is a deliberate
simplification that drops the paid Azure dependency).

Field names below were confirmed by reading the installed package source
directly (docling 2.133.0 / docling-core 2.99.0) — Docling's structured-
output shape has changed across recent releases, so a version bump here
should come with a re-check of this module, not just a version-string edit
in pyproject.toml.
"""

import asyncio
import math
from io import BytesIO

from docling.datamodel.base_models import DocumentStream
from docling.document_converter import DocumentConverter
from docling_core.types.doc import DoclingDocument, TableItem

_converter = DocumentConverter()


class ParsedPage:
    def __init__(self, page_no: int, ocr_confidence: float | None) -> None:
        self.page_no = page_no
        self.ocr_confidence = ocr_confidence


class ParsedTable:
    def __init__(self, page_no: int, cells: dict[str, object]) -> None:
        self.page_no = page_no
        self.cells = cells


class ParsedDocument:
    def __init__(
        self,
        docling_doc: DoclingDocument,
        pages: list[ParsedPage],
        tables: list[ParsedTable],
    ) -> None:
        self.docling_doc = docling_doc
        self.pages = pages
        self.tables = tables


def _parse_sync(filename: str, file_bytes: bytes) -> ParsedDocument:
    stream = DocumentStream(name=filename, stream=BytesIO(file_bytes))
    result = _converter.convert(stream)
    doc = result.document

    # ocr_score defaults to float('nan') (not None) when a page never went
    # through OCR — confirmed by reading PageConfidenceScores' source.
    # NaN would otherwise flow straight into page.ocr_confidence, and
    # Postgres' `ocr_confidence BETWEEN 0 AND 1` CHECK evaluates false (not
    # true) against NaN, so the insert would fail outright.
    pages = [
        ParsedPage(
            page_no=page_no,
            ocr_confidence=None if math.isnan(scores.ocr_score) else scores.ocr_score,
        )
        for page_no, scores in result.confidence.pages.items()
    ]
    scored_page_nos = {p.page_no for p in pages}
    for page_no in doc.pages:
        if page_no not in scored_page_nos:
            pages.append(ParsedPage(page_no=page_no, ocr_confidence=None))

    tables: list[ParsedTable] = []
    for item, _level in doc.iterate_items():
        if isinstance(item, TableItem):
            table_page_no = item.prov[0].page_no if item.prov else None
            if table_page_no is not None:
                tables.append(
                    ParsedTable(page_no=table_page_no, cells=item.data.model_dump(mode="json"))
                )

    return ParsedDocument(docling_doc=doc, pages=pages, tables=tables)


async def parse_document(filename: str, file_bytes: bytes) -> ParsedDocument:
    """Docling's `convert()` is synchronous and CPU-bound (runs OCR/layout
    models); pushed to a thread so it doesn't block the event loop, same
    reasoning as storage.py's boto3 calls and knowledge/embedding.py's
    model inference."""
    return await asyncio.to_thread(_parse_sync, filename, file_bytes)
