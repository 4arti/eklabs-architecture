import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _database_url() -> str:
    url = os.environ.get("APP_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "APP_DATABASE_URL is not set — needs the eklabs_app connection string "
            "(Supabase's transaction-mode pooler, not the direct/session connection "
            "used by Alembic)."
        )
    return url


engine: AsyncEngine = create_async_engine(_database_url(), pool_pre_ping=True)
_session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def tenant_scoped_session(tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Open a session whose entire transaction is scoped to one tenant for RLS.

    `set_config(..., is_local=true)` mirrors `SET LOCAL`'s transaction-scoped
    reset — required because the underlying connection comes from a pool
    shared across requests/tenants (Supabase's transaction-mode pooler), so
    anything session-scoped would leak tenant context into the next request
    on the same pooled connection. This only holds if the `set_config` call
    and every subsequent query run in the SAME transaction, which is exactly
    what this context manager guarantees by setting it immediately inside
    `session.begin()`, before yielding the session to the caller.
    """
    async with _session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_id)},
        )
        yield session
