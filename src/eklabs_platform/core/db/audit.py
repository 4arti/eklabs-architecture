import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eklabs_platform.core.db.models.audit_log import AuditLog

# Chain start for a tenant's very first audit_log row.
_GENESIS_HASH = "0" * 64


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


async def record_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: uuid.UUID,
    action: str,
    target_table: str,
    target_id: uuid.UUID,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    """The only sanctioned way to write an audit_log row.

    Locks the latest row for this tenant (SELECT ... FOR UPDATE) before
    computing the next hash, so two concurrent writers in the same tenant
    can't both read the same "latest" row and fork the chain. The hash
    covers the event's content, not its DB-assigned id/seq (unknown before
    insert) — the chain itself, not an embedded sequence number, is what
    makes reordering or deletion detectable.
    """
    latest = await session.scalar(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.seq.desc())
        .limit(1)
        .with_for_update()
    )
    prev_hash = latest.hash if latest is not None else _GENESIS_HASH
    at = datetime.now(UTC)

    payload = {
        "tenant_id": str(tenant_id),
        "actor": str(actor),
        "action": action,
        "target_table": target_table,
        "target_id": str(target_id),
        "before": before,
        "after": after,
        "at": at.isoformat(),
        "prev_hash": prev_hash,
    }
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    entry = AuditLog(
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        target_table=target_table,
        target_id=target_id,
        before=before,
        after=after,
        at=at,
        prev_hash=prev_hash,
        hash=digest,
    )
    session.add(entry)
    await session.flush()
    return entry
