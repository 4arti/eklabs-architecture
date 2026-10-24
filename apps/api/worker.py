"""The arq worker process. Run from the repo root: `arq apps.api.worker.WorkerSettings`
(not installed as a package, same as how `alembic` resolves `migrations/`
via `prepend_sys_path` — this relies on the repo root being on `sys.path`,
true for both `alembic` and `arq`'s own CLI when invoked from there).

Lives in `apps/api/`, not `eklabs_platform/`, per CLAUDE.md's own repo
layout: `apps/api` is "FastAPI app + background worker" — the process
entrypoint, not the reusable library. No FastAPI app exists yet; this file
is `apps/api`'s first real content.
"""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import ClassVar

from arq.connections import RedisSettings
from dotenv import load_dotenv

# arq is its own process entry point too — and unlike conftest.py's call,
# this one has to run before the import below: `jobs.py` transitively
# imports core/db/session.py (a module-level engine needing
# APP_DATABASE_URL), and WorkerSettings' own class body calls
# redis_settings() needing REDIS_URL, both at this file's import time.
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from eklabs_platform.ingestion.jobs import ingest_document_job, redis_settings
from eklabs_platform.knowledge.embedding import get_embedding_model


async def _startup(ctx: dict[str, object]) -> None:
    # Warms the ~1.3GB BGE model once, on worker startup, rather than
    # paying that cost on whichever job happens to run first.
    get_embedding_model()


class WorkerSettings:
    functions: ClassVar[list[Callable[..., Awaitable[object]]]] = [ingest_document_job]
    redis_settings: RedisSettings = redis_settings()
    on_startup = _startup
