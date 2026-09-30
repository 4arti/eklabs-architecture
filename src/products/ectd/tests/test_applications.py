import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from eklabs_platform.core.db.session import tenant_scoped_session
from products.ectd.applications import create_application
from products.ectd.db.models.application import Application
from products.ectd.db.models.section import Section
from products.ectd.format_policy import InvalidFormatCombinationError

from .conftest import ROW_FACTORIES

# No async marker needed: pyproject.toml sets asyncio_mode = "auto".

# Checked via .orig.sqlstate, not isinstance(.orig, asyncpg.exceptions.X) —
# see eklabs_platform's test_tenant_isolation.py for the full rationale
# (SQLAlchemy's asyncpg dialect wraps every asyncpg exception in its own
# same-named class, so isinstance against asyncpg.exceptions.X never
# matches; .sqlstate is preserved and is the stable thing to assert on).
SQLSTATE_FOREIGN_KEY_VIOLATION = "23503"
SQLSTATE_CHECK_VIOLATION = "23514"


@pytest.mark.parametrize("table_name", sorted(ROW_FACTORIES))
async def test_cross_tenant_read_is_blocked(
    table_name: str,
    make_tenant: Callable[[], Awaitable[uuid.UUID]],
) -> None:
    """Same proof as the platform suite, for the 3 new tables — see
    eklabs_platform's test_tenant_isolation.py for the full rationale."""
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


async def test_cross_tenant_insert_blocked_by_composite_fk_application_to_product(
    make_tenant: Callable[[], Awaitable[uuid.UUID]],
) -> None:
    tenant_a = await make_tenant()
    tenant_b = await make_tenant()

    async with tenant_scoped_session(tenant_a) as session:
        tenant_a_product_id = await ROW_FACTORIES["product"](session, tenant_a)

    async with tenant_scoped_session(tenant_b) as session:
        with pytest.raises(DBAPIError) as excinfo:
            session.add(
                Application(
                    tenant_id=tenant_b,
                    product_id=tenant_a_product_id,
                    authority="US-FDA",
                    app_type="nda_505b1",
                    format="ectd_4_0",
                    profile_version="1",
                )
            )
            await session.flush()
        assert getattr(excinfo.value.orig, "sqlstate", None) == SQLSTATE_FOREIGN_KEY_VIOLATION


async def test_cross_tenant_insert_blocked_by_composite_fk_section_to_application(
    make_tenant: Callable[[], Awaitable[uuid.UUID]],
) -> None:
    tenant_a = await make_tenant()
    tenant_b = await make_tenant()

    async with tenant_scoped_session(tenant_a) as session:
        tenant_a_application_id = await ROW_FACTORIES["application"](session, tenant_a)

    async with tenant_scoped_session(tenant_b) as session:
        with pytest.raises(DBAPIError) as excinfo:
            session.add(
                Section(
                    tenant_id=tenant_b,
                    application_id=tenant_a_application_id,
                    ctd_code="3.2.P.5.1",
                )
            )
            await session.flush()
        assert getattr(excinfo.value.orig, "sqlstate", None) == SQLSTATE_FOREIGN_KEY_VIOLATION


async def test_create_application_valid_combination_succeeds(
    make_tenant: Callable[[], Awaitable[uuid.UUID]],
) -> None:
    tenant_a = await make_tenant()
    async with tenant_scoped_session(tenant_a) as session:
        product_id = await ROW_FACTORIES["product"](session, tenant_a)
        application = await create_application(
            session,
            tenant_id=tenant_a,
            product_id=product_id,
            authority="US-FDA",
            app_type="nda_505b1",
            format="ectd_4_0",
            situation="new_application",
        )
        assert application.profile_version == "1"
        assert application.format == "ectd_4_0"


async def test_create_application_rejects_disallowed_format_for_situation(
    make_tenant: Callable[[], Awaitable[uuid.UUID]],
) -> None:
    tenant_a = await make_tenant()
    async with tenant_scoped_session(tenant_a) as session:
        product_id = await ROW_FACTORIES["product"](session, tenant_a)
        with pytest.raises(InvalidFormatCombinationError):
            await create_application(
                session,
                tenant_id=tenant_a,
                product_id=product_id,
                authority="US-FDA",
                app_type="nda_505b1",
                format="ctd_pdf",
                situation="new_application",
            )
        existing = await session.scalar(
            select(Application.id).where(Application.product_id == product_id)
        )
        assert existing is None, "rejected combination must not insert a row"


async def test_create_application_rejects_unknown_app_type(
    make_tenant: Callable[[], Awaitable[uuid.UUID]],
) -> None:
    """This is the case that specifically proves the no-DB-CHECK path is
    actually enforced — app_type has no CHECK constraint, so nothing in
    Postgres would catch a bad value on its own."""
    tenant_a = await make_tenant()
    async with tenant_scoped_session(tenant_a) as session:
        product_id = await ROW_FACTORIES["product"](session, tenant_a)
        with pytest.raises(InvalidFormatCombinationError):
            await create_application(
                session,
                tenant_id=tenant_a,
                product_id=product_id,
                authority="US-FDA",
                app_type="not_a_real_app_type",
                format="ectd_4_0",
                situation="new_application",
            )
        existing = await session.scalar(
            select(Application.id).where(Application.product_id == product_id)
        )
        assert existing is None, "rejected combination must not insert a row"


async def test_bogus_format_bypassing_service_layer_hits_db_check(
    make_tenant: Callable[[], Awaitable[uuid.UUID]],
) -> None:
    """Proves the format CHECK constraint itself, independent of app code —
    a raw insert that skips create_application()/format_policy() entirely."""
    tenant_a = await make_tenant()
    async with tenant_scoped_session(tenant_a) as session:
        product_id = await ROW_FACTORIES["product"](session, tenant_a)
        with pytest.raises(DBAPIError) as excinfo:
            session.add(
                Application(
                    tenant_id=tenant_a,
                    product_id=product_id,
                    authority="US-FDA",
                    app_type="nda_505b1",
                    format="not_real",
                    profile_version="1",
                )
            )
            await session.flush()
        assert getattr(excinfo.value.orig, "sqlstate", None) == SQLSTATE_CHECK_VIOLATION
