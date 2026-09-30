import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from eklabs_platform.core.db.audit import record_event
from eklabs_platform.core.db.models.app_user import AppUser
from eklabs_platform.core.db.models.chunk import Chunk
from eklabs_platform.core.db.models.document import Document
from eklabs_platform.core.db.models.page import Page
from eklabs_platform.core.db.models.tenant import Tenant
from eklabs_platform.core.db.session import tenant_scoped_session

# _migrated_db (the alembic-upgrade-head autouse fixture) lives in the
# root-level conftest.py instead of here — it needs to cascade to
# src/products/ectd/tests/ too, which isn't a descendant of this directory,
# so pytest's directory-tree-based conftest inheritance can't reach it from
# here. Root conftest.py is still an ancestor of this directory, so nothing
# below loses access to it.


@pytest.fixture
async def make_tenant() -> Callable[[], Awaitable[uuid.UUID]]:
    """Inserts a bare tenant row.

    The id is generated client-side (not left to the server default) and
    the session is scoped to that same id *before* inserting — required,
    not just tidy. SQLAlchemy auto-appends `RETURNING id, created_at` to
    fetch server-generated values, and under RLS a RETURNING clause is
    implicitly subject to the table's SELECT policy too (`id =
    current_setting('app.tenant_id')`). tenant's INSERT policy is
    unconditional (WITH CHECK (true)), but if the session were scoped to an
    unrelated tenant_id, the newly-inserted row wouldn't satisfy the SELECT
    policy and Postgres raises "new row violates row-level security policy"
    on the RETURNING, not the INSERT itself — this bit us for real the
    first time this fixture actually ran against a live database. The same
    constraint applies to any future production tenant-signup code that
    goes through tenant_scoped_session, not just this fixture.
    """

    async def _make() -> uuid.UUID:
        suffix = uuid.uuid4().hex
        new_id = uuid.uuid4()
        async with tenant_scoped_session(new_id) as session:
            tenant = Tenant(id=new_id, name=f"Test Tenant {suffix}", slug=f"test-tenant-{suffix}")
            session.add(tenant)
            await session.flush()
            return tenant.id

    return _make


async def _make_app_user(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    suffix = uuid.uuid4().hex
    user = AppUser(
        tenant_id=tenant_id,
        external_auth_id=f"clerk_{suffix}",
        email=f"{suffix}@example.com",
    )
    session.add(user)
    await session.flush()
    return user.id


async def _make_document(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    suffix = uuid.uuid4().hex
    document = Document(
        tenant_id=tenant_id,
        title="Test document",
        file_type="pdf",
        s3_key=f"docs/{suffix}.pdf",
        sha256=suffix,
    )
    session.add(document)
    await session.flush()
    return document.id


async def _make_page(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    document_id = await _make_document(session, tenant_id)
    page = Page(tenant_id=tenant_id, document_id=document_id, page_no=1)
    session.add(page)
    await session.flush()
    return page.id


async def _make_chunk(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    document_id = await _make_document(session, tenant_id)
    chunk = Chunk(tenant_id=tenant_id, document_id=document_id, text="hello world")
    session.add(chunk)
    await session.flush()
    return chunk.id


async def _make_audit_log(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    actor_id = await _make_app_user(session, tenant_id)
    entry = await record_event(
        session,
        tenant_id=tenant_id,
        actor=actor_id,
        action="test.create",
        target_table="document",
        target_id=uuid.uuid4(),
    )
    return entry.id


# One row-factory per tenant-scoped table (tenant itself is excluded — its
# RLS design is scoped to its own id, not a tenant_id column, so it's tested
# separately). Each factory creates whatever parent rows it needs (page and
# chunk each need a document; audit_log needs an app_user as its actor) so
# every table can be exercised through the same generic assertion logic
# instead of near-duplicate tests per table.
ROW_FACTORIES: dict[str, Callable[[AsyncSession, uuid.UUID], Awaitable[uuid.UUID]]] = {
    "app_user": _make_app_user,
    "document": _make_document,
    "page": _make_page,
    "chunk": _make_chunk,
    "audit_log": _make_audit_log,
}
