import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

# make_tenant and _migrated_db are reused as-is: products importing platform
# test helpers is fine (only the reverse direction is the hard rule).
# make_tenant re-exported here (not just imported) so pytest sees it as a
# fixture in this package too — noqa since it's used only by name injection.
from eklabs_platform.core.tests.conftest import make_tenant  # noqa: F401
from products.ectd.db.models.application import Application
from products.ectd.db.models.product import Product
from products.ectd.db.models.section import Section


async def _make_product(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    suffix = uuid.uuid4().hex
    product = Product(
        tenant_id=tenant_id,
        name=f"Test Product {suffix}",
        dosage_form="tablet",
        strength="10 mg",
        product_class="small_molecule",
    )
    session.add(product)
    await session.flush()
    return product.id


async def _make_application(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    product_id = await _make_product(session, tenant_id)
    application = Application(
        tenant_id=tenant_id,
        product_id=product_id,
        authority="US-FDA",
        app_type="nda_505b1",
        format="ectd_4_0",
        profile_version="1",
    )
    session.add(application)
    await session.flush()
    return application.id


async def _make_section(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    application_id = await _make_application(session, tenant_id)
    section = Section(tenant_id=tenant_id, application_id=application_id, ctd_code="3.2.P.5.1")
    session.add(section)
    await session.flush()
    return section.id


# Same shape as eklabs_platform.core.tests.conftest.ROW_FACTORIES — can't be
# extended across the package boundary (products can't add to platform's
# dict from here without platform importing products), so it's a small,
# intentional duplicate of that pattern, not a real DRY violation.
ROW_FACTORIES: dict[str, Callable[[AsyncSession, uuid.UUID], Awaitable[uuid.UUID]]] = {
    "product": _make_product,
    "application": _make_application,
    "section": _make_section,
}
