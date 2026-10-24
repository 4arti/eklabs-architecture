"""Self-hosted embeddings — BAAI/bge-large-en-v1.5 (MIT-licensed), chosen
over spec §1's Voyage AI specifically because it's free (no API key, no
usage cap) and its 1024-dim output matches `chunk.embedding`
(`Vector(1024)`, migration 0002) with zero schema change.

BGE's convention is asymmetric: queries get an instruction prefix, passages
(the text actually being indexed) get none. Getting this backwards doesn't
error — it just quietly degrades retrieval quality, so both functions below
exist precisely to make the two paths impossible to mix up at a call site.
"""

import asyncio
import functools

from sentence_transformers import SentenceTransformer

# Public: ingestion/chunking.py also needs this, to seed HybridChunker
# with BGE's own tokenizer rather than a generic one.
MODEL_NAME = "BAAI/bge-large-en-v1.5"
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@functools.lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Lazy, not an eager module-level singleton: this loads ~1.3GB of
    model weights on first call. An eager load would fire on any import of
    this module — including transitively, from pytest collection — which
    is wrong for something this heavy and not universally needed."""
    return SentenceTransformer(MODEL_NAME)


def _encode(texts: list[str]) -> list[list[float]]:
    # SentenceTransformer.encode() is synchronous and CPU/GPU-bound; the
    # async wrappers below push it to a thread so it doesn't block the
    # event loop (same reasoning as storage.py's boto3 calls, and the
    # ingestion pipeline's Docling calls).
    model = get_embedding_model()
    vectors = model.encode(texts, normalize_embeddings=True)
    return [vector.tolist() for vector in vectors]


async def embed_passages(texts: list[str]) -> list[list[float]]:
    """For text being indexed (chunks) — no instruction prefix."""
    return await asyncio.to_thread(_encode, texts)


async def embed_query(text: str) -> list[float]:
    """For a search query — BGE's required instruction prefix."""
    vectors = await asyncio.to_thread(_encode, [_QUERY_PREFIX + text])
    return vectors[0]
