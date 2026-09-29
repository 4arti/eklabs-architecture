import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession

from eklabs_platform.core.db.audit import record_event
from eklabs_platform.core.db.models.app_user import AppUser
from eklabs_platform.core.db.models.chunk import Chunk
from eklabs_platform.core.db.models.document import Document
from eklabs_platform.core.db.models.page import Page
from eklabs_platform.core.db.models.tenant import Tenant
from eklabs_platform.core.db.session import tenant_scoped_session

# src/platform/core/tests/conftest.py -> tests -> core -> platform -> src -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="session", autouse=True)
def _migrated_db() -> None:
    """Runs `alembic upgrade head` once per test session, against
    ALEMBIC_DATABASE_URL (eklabs_migrator), so `pytest` alone reproduces the
    environment — no separate manual migration step for a contributor."""
    config = Config(str(_REPO_ROOT / "alembic.ini"))
    command.upgrade(config, "head")


@pytest.fixture
async def make_tenant() -> Callable[[], Awaitable[uuid.UUID]]:
    """Inserts a bare tenant row. tenant's INSERT policy is unconditional
    (WITH CHECK (true) — provisioning necessarily precedes any tenant
    context), so which tenant_id tenant_scoped_session is opened with here
    is irrelevant; a fresh random one is used only because the helper needs
    one."""

    async def _make() -> uuid.UUID:
        suffix = uuid.uuid4().hex
        async with tenant_scoped_session(uuid.uuid4()) as session:
            tenant = Tenant(name=f"Test Tenant {suffix}", slug=f"test-tenant-{suffix}")
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
