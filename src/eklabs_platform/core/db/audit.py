import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
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

    Serializes concurrent writers for this tenant via a transaction-scoped
    Postgres advisory lock (released automatically at commit/rollback,
    same lifetime a row lock would have had), not a SELECT ... FOR UPDATE
    row lock — eklabs_app deliberately has no UPDATE grant on audit_log
    (that's the actual mechanism behind the append-only guarantee, see
    test_audit_log_is_append_only), and Postgres requires UPDATE privilege
    for FOR UPDATE row locks even though no UPDATE statement ever runs
    here. Advisory locks aren't gated by table ACLs at all, so this
    achieves the same "don't let two writers fork the hash chain"
    serialization without granting anything that would also legitimize a
    real UPDATE. hashtext() collisions just mean two unrelated tenants'
    writes occasionally serialize against each other unnecessarily — a
    performance hiccup, never a correctness issue.
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:tenant_id))"),
        {"tenant_id": str(tenant_id)},
    )
    latest = await session.scalar(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.seq.desc())
        .limit(1)
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
