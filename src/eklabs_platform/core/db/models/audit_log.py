import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKeyConstraint, Identity, Index, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from eklabs_platform.core.db.base import Base
from eklabs_platform.core.db.mixins import TenantScopedMixin, UUIDPkMixin


class AuditLog(Base, UUIDPkMixin, TenantScopedMixin):
    """Append-only, hash-chained audit trail (spec §4, §13 Part-11-ready).

    Append-only is enforced by grants in the migration (eklabs_app gets
    SELECT, INSERT only — no UPDATE/DELETE granted at all), not by anything
    in this model. The hash chain itself (prev_hash -> hash) is computed by
    record_event() in db/audit.py, the one sanctioned writer for this table;
    hashing only makes tampering *detectable*, the grants make it
    *impossible* for the app role.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        # An audit row can never be attributed to another tenant's user.
        ForeignKeyConstraint(["actor", "tenant_id"], ["app_user.id", "app_user.tenant_id"]),
        Index("ix_audit_log_tenant_id_seq", "tenant_id", "seq"),
        Index("ix_audit_log_target", "target_table", "target_id"),
    )

    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)
    actor: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    action: Mapped[str] = mapped_column(nullable=False)
    # Split out of spec §4's single `target` column for queryability. No FK
    # on target_id — deliberately polymorphic across every tenant-scoped
    # table (including future product tables); referential integrity there
    # is an application concern, not the database's.
    target_table: Mapped[str] = mapped_column(nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    prev_hash: Mapped[str | None]
    hash: Mapped[str] = mapped_column(nullable=False)
