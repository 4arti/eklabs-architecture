from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from eklabs_platform.core.db.base import Base
from eklabs_platform.core.db.mixins import UUIDPkMixin


class Tenant(Base, UUIDPkMixin):
    """The tenant identity itself.

    No tenant_id column (its own id *is* the tenant identity) and no blanket
    RLS policy like the other five tables — the migration instead gives it
    two narrower policies: SELECT/UPDATE scoped to `id = current tenant`, and
    a permissive INSERT, since tenant provisioning necessarily happens before
    any tenant context exists to scope against.
    """

    __tablename__ = "tenant"

    name: Mapped[str] = mapped_column(nullable=False)
    slug: Mapped[str] = mapped_column(unique=True, nullable=False)
    # Clerk org id (spec §1: Clerk for auth/organisations). Nullable: a tenant
    # row can be provisioned slightly before its Clerk org is linked.
    clerk_org_id: Mapped[str | None] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
