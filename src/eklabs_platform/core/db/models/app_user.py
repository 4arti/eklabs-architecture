from datetime import datetime

from sqlalchemy import Boolean, ForeignKeyConstraint, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from eklabs_platform.core.db.base import Base
from eklabs_platform.core.db.mixins import TenantScopedMixin, UUIDPkMixin


class AppUser(Base, UUIDPkMixin, TenantScopedMixin):
    """A person within one tenant. No `role` column yet — role_binding is a
    separate, later slice; nothing is authorized against this table yet."""

    __tablename__ = "app_user"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        # Named explicitly: both start with tenant_id, and the naming
        # convention in base.py keys "uq" off the first column only, so
        # left to autogenerate these two would collide on the same name.
        UniqueConstraint(
            "tenant_id", "external_auth_id", name="uq_app_user_tenant_id_external_auth_id"
        ),
        UniqueConstraint("tenant_id", "email", name="uq_app_user_tenant_id_email"),
        # Composite-FK target for audit_log.actor.
        UniqueConstraint("id", "tenant_id"),
    )

    # Clerk user id (spec §1).
    external_auth_id: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(nullable=False)
    display_name: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
