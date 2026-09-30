import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from eklabs_platform.core.db.base import Base
from eklabs_platform.core.db.mixins import TenantScopedMixin, UUIDPkMixin

STATUSES = ("empty", "drafting", "in_review", "approved")


class Section(Base, UUIDPkMixin, TenantScopedMixin):
    """One CTD section placeholder within an application (spec §4).

    status/template_version are the fields legitimately mutated in place
    (mirrors document.status's exception) — the section's actual authored
    content lives in section_version (Week 6+), never here.
    """

    __tablename__ = "section"
    __table_args__ = (
        ForeignKeyConstraint(
            ["application_id", "tenant_id"], ["application.id", "application.tenant_id"]
        ),
        # Composite-FK target for section_version.section_id, once that
        # table exists (Week 6+) — cheap to add now, disruptive to retrofit
        # onto a table that already has rows.
        UniqueConstraint("id", "tenant_id"),
        UniqueConstraint("application_id", "ctd_code"),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in STATUSES) + ")",
            name="status_valid",
        ),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # e.g. '3.2.P.5.1' — no CHECK, far too many valid codes across modules.
    ctd_code: Mapped[str] = mapped_column(nullable=False)
    # Nullable: no template chosen until the planner agent (Week 12) or a
    # manual pick.
    template_version: Mapped[str | None]
    status: Mapped[str] = mapped_column(nullable=False, server_default="empty")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
