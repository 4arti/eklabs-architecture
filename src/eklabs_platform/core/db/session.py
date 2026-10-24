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


# statement_cache_size=0 disables asyncpg's client-side prepared-statement
# cache — required against Supabase's transaction-mode pooler (PgBouncer).
# PgBouncer in transaction mode can route a query to a different physical
# backend connection than the one that originally prepared a statement, and
# that backend may coincidentally already have a statement under the same
# auto-generated name (__asyncpg_stmt_N__) prepared by some other, unrelated
# session that previously shared it — asyncpg has no way to know, and
# raises DuplicatePreparedStatementError. This is a documented asyncpg/
# PgBouncer incompatibility, not something APP_DATABASE_URL's own queries
# did wrong; confirmed by hitting it for real once enough distinct
# tenant_scoped_session() calls had run against the pooler for backend
# rotation to actually occur.
engine: AsyncEngine = create_async_engine(
    _database_url(), pool_pre_ping=True, connect_args={"statement_cache_size": 0}
)
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
