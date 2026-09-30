import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from eklabs_platform.core.db.models.page import Page
from eklabs_platform.core.db.session import tenant_scoped_session

from .conftest import ROW_FACTORIES

# No async marker needed: pyproject.toml sets asyncio_mode = "auto", so
# pytest-asyncio treats every `async def test_*` here as an asyncio test.

# Checked via .orig.sqlstate, not isinstance(.orig, asyncpg.exceptions.X):
# SQLAlchemy's asyncpg dialect translates every asyncpg exception into its
# own parallel class hierarchy (sqlalchemy.dialects.postgresql.asyncpg.X,
# confirmed by reading that module's source) — .orig is that translated
# wrapper, never the raw asyncpg exception, so isinstance against
# asyncpg.exceptions.X can never match. sqlstate is explicitly preserved by
# the wrapper (`self.pgcode = self.sqlstate = getattr(error, "sqlstate",
# None)`), so it's the stable, driver/wrapper-agnostic way to check this —
# these are the standard Postgres error codes, not something of ours.
SQLSTATE_INSUFFICIENT_PRIVILEGE = "42501"
SQLSTATE_FOREIGN_KEY_VIOLATION = "23503"


@pytest.mark.parametrize("table_name", sorted(ROW_FACTORIES))
async def test_cross_tenant_read_is_blocked(
    table_name: str,
    make_tenant: Callable[[], Awaitable[uuid.UUID]],
) -> None:
    """Row-level security must make tenant B's row invisible to tenant A —
    not just filtered out of a list, but absent even from a direct
    primary-key lookup. Each test run uses brand-new tenants, so a plain
    unscoped count(*) scoped to tenant A is exact regardless of what other
    tests have inserted into the same table."""
    tenant_a = await make_tenant()
    tenant_b = await make_tenant()
    factory = ROW_FACTORIES[table_name]

    async with tenant_scoped_session(tenant_a) as session:
        await factory(session, tenant_a)

    async with tenant_scoped_session(tenant_b) as session:
        tenant_b_row_id = await factory(session, tenant_b)

    async with tenant_scoped_session(tenant_a) as session:
        count = await session.scalar(text(f"SELECT count(*) FROM {table_name}"))
        assert count == 1, f"expected exactly tenant A's own row in {table_name}, got {count}"

        invisible = await session.execute(
            text(f"SELECT id FROM {table_name} WHERE id = :id"), {"id": tenant_b_row_id}
        )
        assert invisible.first() is None, (
            f"tenant A could read tenant B's {table_name} row by id — RLS is not enforcing isolation"
        )


async def test_audit_log_is_append_only(
    make_tenant: Callable[[], Awaitable[uuid.UUID]],
) -> None:
    """audit_log's append-only guarantee comes from grants (eklabs_app has
    no UPDATE/DELETE on this table at all), not from the hash chain — the
    hash only makes tampering *detectable*. This is what actually proves
    that at the database layer."""
    tenant_a = await make_tenant()

    async with tenant_scoped_session(tenant_a) as session:
        entry_id = await ROW_FACTORIES["audit_log"](session, tenant_a)

    async with tenant_scoped_session(tenant_a) as session:
        with pytest.raises(DBAPIError) as excinfo:
            await session.execute(
                text("UPDATE audit_log SET action = 'tampered' WHERE id = :id"), {"id": entry_id}
            )
        assert getattr(excinfo.value.orig, "sqlstate", None) == SQLSTATE_INSUFFICIENT_PRIVILEGE

    # Separate session/transaction: the one above is aborted by the error
    # above (Postgres refuses further statements in a failed transaction).
    async with tenant_scoped_session(tenant_a) as session:
        with pytest.raises(DBAPIError) as excinfo:
            await session.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": entry_id})
        assert getattr(excinfo.value.orig, "sqlstate", None) == SQLSTATE_INSUFFICIENT_PRIVILEGE


async def test_cross_tenant_insert_blocked_by_composite_fk(
    make_tenant: Callable[[], Awaitable[uuid.UUID]],
) -> None:
    """page's composite FK is (document_id, tenant_id) -> document(id,
    tenant_id) — a row claiming tenant B's tenant_id but pointing at tenant
    A's document must fail at the database level, not merely be filtered by
    RLS after the fact."""
    tenant_a = await make_tenant()
    tenant_b = await make_tenant()

    async with tenant_scoped_session(tenant_a) as session:
        tenant_a_document_id = await ROW_FACTORIES["document"](session, tenant_a)

    async with tenant_scoped_session(tenant_b) as session:
        with pytest.raises(DBAPIError) as excinfo:
            session.add(Page(tenant_id=tenant_b, document_id=tenant_a_document_id, page_no=1))
            await session.flush()
        assert getattr(excinfo.value.orig, "sqlstate", None) == SQLSTATE_FOREIGN_KEY_VIOLATION
