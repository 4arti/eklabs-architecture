"""Arq wiring for `ingestion.pipeline.ingest_document()`. All real logic
lives in `pipeline.py`, which has no arq import at all and is directly
callable/testable with a plain session — this module is only the thin
invoker arq needs, plus the enqueue-side helper.
"""

import os
import uuid
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings

from eklabs_platform.core.db.session import tenant_scoped_session
from eklabs_platform.ingestion.pipeline import ingest_document


# Public: apps/api/worker.py's WorkerSettings needs this too.
def redis_settings() -> RedisSettings:
    url = os.environ.get("REDIS_URL")
    if not url:
        raise RuntimeError("REDIS_URL is not set.")
    return RedisSettings.from_dsn(url)


async def ingest_document_job(
    ctx: dict[str, Any], *, document_id: str, tenant_id: str, actor: str
) -> None:
    """The job function `apps/api/worker.py`'s `WorkerSettings` registers.
    UUIDs cross the arq/Redis boundary as strings (job args get
    JSON-serialized), converted back here."""
    async with tenant_scoped_session(uuid.UUID(tenant_id)) as session:
        await ingest_document(
            session,
            tenant_id=uuid.UUID(tenant_id),
            actor=uuid.UUID(actor),
            document_id=uuid.UUID(document_id),
        )


async def enqueue_ingest_document(
    *, document_id: uuid.UUID, tenant_id: uuid.UUID, actor: uuid.UUID
) -> None:
    """Called right after `core.documents.register_document()` — the only
    place that should ever enqueue this job."""
    redis = await create_pool(redis_settings())
    try:
        await redis.enqueue_job(
            "ingest_document_job",
            document_id=str(document_id),
            tenant_id=str(tenant_id),
            actor=str(actor),
        )
    finally:
        await redis.close()
