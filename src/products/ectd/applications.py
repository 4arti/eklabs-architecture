"""create_application() is the one sanctioned writer for the `application`
table, mirroring eklabs_platform.core.db.audit::record_event() — every
future caller (wizard, API, publisher) should go through this function,
never insert an Application row directly, since this is where FormatPolicy
actually gets enforced. There is no database CHECK backstop for app_type
(see db/models/application.py), so this function is the only thing standing
between a bad combination and a written row.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from products.ectd.db.models.application import Application
from products.ectd.format_policy import validate_application_format
from products.ectd.profiles.loader import load_profile


async def create_application(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    authority: str,
    app_type: str,
    format: str,
    situation: str,
    app_number: str | None = None,
) -> Application:
    """Validates (authority, app_type, format, situation) via format_policy()
    before touching the database. Raises InvalidFormatCombinationError and
    inserts nothing if the combination isn't allowed."""
    validate_application_format(authority, app_type, format, situation)
    profile = load_profile(authority)

    application = Application(
        tenant_id=tenant_id,
        product_id=product_id,
        authority=authority,
        app_type=app_type,
        format=format,
        profile_version=profile.version,
        app_number=app_number,
    )
    session.add(application)
    await session.flush()
    return application
