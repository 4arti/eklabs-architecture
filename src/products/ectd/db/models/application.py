import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from eklabs_platform.core.db.base import Base
from eklabs_platform.core.db.mixins import TenantScopedMixin, UUIDPkMixin

# Fixed, closed set shared by every authority — safe to enforce with a DB
# CHECK, unlike app_type (see the module docstring below).
FORMATS = ("ctd_pdf", "ectd_3_2_2", "ectd_4_0")


class Application(Base, UUIDPkMixin, TenantScopedMixin):
    """One submission attempt for a product, to one authority (spec §4).

    app_type deliberately has NO database CHECK constraint, unlike format.
    A CHECK can only see this row's own columns — it has no way to know
    *which authority's* list of valid app_types applies, and the real
    invariant is "app_type is valid for this row's authority," a
    cross-referenced, per-authority rule. The only CHECK that could ever be
    written would be the union of every authority's app_types, which would
    wrongly accept e.g. 'anda' on an EU application. Enforcement is 100% in
    format_policy.py / applications.py::create_application() — there is no
    database backstop for a bad app_type, by design.
    """

    __tablename__ = "application"
    __table_args__ = (
        ForeignKeyConstraint(["product_id", "tenant_id"], ["product.id", "product.tenant_id"]),
        # Composite-FK target for section.application_id.
        UniqueConstraint("id", "tenant_id"),
        CheckConstraint(
            "format IN (" + ", ".join(f"'{f}'" for f in FORMATS) + ")",
            name="format_valid",
        ),
        Index("ix_application_tenant_id_product_id", "tenant_id", "product_id"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # Profile lookup key, e.g. 'US-FDA'.
    authority: Mapped[str] = mapped_column(nullable=False)
    app_type: Mapped[str] = mapped_column(nullable=False)
    format: Mapped[str] = mapped_column(nullable=False)
    # Which version of the authority's profile was used to validate this
    # application at creation time — for audit/reproducibility.
    profile_version: Mapped[str] = mapped_column(nullable=False)
    # Nullable: the agency assigns this via a separate pre-assignment
    # request, not known at record-creation time.
    app_number: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Unlike product, an application's format can legitimately change after
    # creation (the profile's "existing_3_2_2_application" situation only
    # makes sense if a format transition is a real, supported path) — a
    # genuine mutation, same shape as document.status.
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
