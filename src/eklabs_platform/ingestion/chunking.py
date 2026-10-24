"""Chunks a parsed Docling document into retrievable text slices.

Uses Docling's own `HybridChunker` rather than a hand-rolled chunker — it
already does what spec §6 requires ("a table is never split mid-row"): an
oversized table gets split by whole rows with the header repeated in each
piece, never mid-row. The chunker is tokenizer-aware, so it's seeded with
BGE's own tokenizer (not a generic one) — chunk sizing needs to respect
BGE-large-en-v1.5's 512-token limit, since that model silently truncates
past it rather than erroring.
"""

import asyncio
import functools
from typing import Any

from docling_core.transforms.chunker import DocChunk
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc.document import DoclingDocument

from eklabs_platform.knowledge.embedding import MODEL_NAME

# Conservatively below BGE's actual 512-token limit. Verified empirically
# against a real 13-page EPAR (31 chunks): HybridChunker's internal
# splitting decisions already measure the *contextualize()'d* text (its
# _count_chunk_tokens helper calls contextualize() before counting), not
# the pre-heading-prefix text — so the margin below isn't needed to cover
# an uncounted prefix, it's just headroom. Max observed: 442 raw tokens
# (the tokenizer's own +2 for BOS/EOS over this budget), well under 512.
_MAX_TOKENS = 440


class ChunkData:
    def __init__(
        self,
        text: str,
        section_path: str | None,
        page: int | None,
        bbox: dict[str, Any] | None,
    ) -> None:
        self.text = text
        self.section_path = section_path
        self.page = page
        self.bbox = bbox


@functools.lru_cache(maxsize=1)
def _get_chunker() -> HybridChunker:
    # max_tokens belongs on the tokenizer, not HybridChunker itself — a
    # HybridChunker(max_tokens=...) kwarg looks plausible but silently hits
    # a deprecated legacy code path instead (confirmed by reading
    # hybrid_chunker.py's source directly).
    tokenizer = HuggingFaceTokenizer.from_pretrained(model_name=MODEL_NAME, max_tokens=_MAX_TOKENS)
    return HybridChunker(tokenizer=tokenizer)


def _chunk_sync(doc: DoclingDocument) -> list[ChunkData]:
    chunker = _get_chunker()
    results: list[ChunkData] = []

    for base_chunk in chunker.chunk(dl_doc=doc):
        # HybridChunker.chunk()'s return type is the generic Iterator[BaseChunk],
        # but it only ever yields DocChunk in practice (confirmed by reading
        # its source) — narrowed explicitly rather than assumed, since
        # DocMeta (doc_items/headings) lives on DocChunk, not the base type.
        if not isinstance(base_chunk, DocChunk):
            raise TypeError(f"Expected a DocChunk from HybridChunker, got {type(base_chunk)!r}")

        text = chunker.contextualize(chunk=base_chunk)

        page: int | None = None
        bbox: dict[str, Any] | None = None
        for item in base_chunk.meta.doc_items:
            if item.prov:
                page = item.prov[0].page_no
                bbox = item.prov[0].bbox.model_dump(mode="json")
                break

        section_path = " > ".join(base_chunk.meta.headings) if base_chunk.meta.headings else None
        results.append(ChunkData(text=text, section_path=section_path, page=page, bbox=bbox))

    return results


async def chunk_document(doc: DoclingDocument) -> list[ChunkData]:
    """CPU-bound (tokenization over the whole document); pushed to a thread
    like every other heavy call in this pipeline."""
    return await asyncio.to_thread(_chunk_sync, doc)
