"""Hybrid search over `chunk` (spec §6: "combines meaning (vectors) and
keywords"). Combines a vector-similarity ranking and a keyword ranking via
reciprocal rank fusion (RRF) — chosen over trying to normalize cosine
distance and `ts_rank` onto the same scale, which don't share one
honestly, whereas combining two *rankings* avoids that problem entirely.

Raw SQL via `text()`, consistent with this codebase's existing style for
anything beyond simple CRUD (see session.py's `set_config` call,
audit.py's advisory lock) — this query's two ranked CTEs aren't natural to
express as SQLAlchemy Core either way.

Relies on RLS for tenant scoping, same as the rest of this codebase — the
caller must already be inside a `tenant_scoped_session(tenant_id)`.
"""

import uuid

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from eklabs_platform.knowledge.embedding import embed_query

# Reciprocal rank fusion constant — the standard choice (used by
# Elasticsearch's own RRF implementation); not tuned for this corpus yet.
_RRF_K = 60

_SEARCH_SQL = text(
    """
    WITH vector_ranked AS (
        SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> (:query_vector)::vector) AS rank
        FROM chunk
        WHERE embedding IS NOT NULL
        LIMIT :candidate_limit
    ),
    keyword_ranked AS (
        SELECT id, ROW_NUMBER() OVER (
            ORDER BY ts_rank(to_tsvector('english', text), plainto_tsquery('english', :raw_query)) DESC
        ) AS rank
        FROM chunk
        WHERE to_tsvector('english', text) @@ plainto_tsquery('english', :raw_query)
        LIMIT :candidate_limit
    )
    SELECT
        c.id, c.document_id, c.text, c.page, c.section_path,
        COALESCE(1.0 / (:rrf_k + v.rank), 0) + COALESCE(1.0 / (:rrf_k + k.rank), 0) AS score
    FROM chunk c
    LEFT JOIN vector_ranked v ON v.id = c.id
    LEFT JOIN keyword_ranked k ON k.id = c.id
    WHERE v.id IS NOT NULL OR k.id IS NOT NULL
    ORDER BY score DESC
    LIMIT :result_limit
    """
)


class SearchResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    text: str
    page: int | None
    section_path: str | None
    score: float


async def search_chunks(
    session: AsyncSession, *, query: str, limit: int = 10, candidate_limit: int = 100
) -> list[SearchResult]:
    query_vector = await embed_query(query)
    rows = await session.execute(
        _SEARCH_SQL,
        {
            "query_vector": str(query_vector),
            "raw_query": query,
            "rrf_k": _RRF_K,
            "candidate_limit": candidate_limit,
            "result_limit": limit,
        },
    )
    return [
        SearchResult(
            chunk_id=row.id,
            document_id=row.document_id,
            text=row.text,
            page=row.page,
            section_path=row.section_path,
            score=row.score,
        )
        for row in rows
    ]
