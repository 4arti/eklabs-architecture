"""platform core tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every table's grant is the same (SELECT, INSERT, UPDATE — no DELETE
# anywhere in this data model) except audit_log, which is append-only.
_STANDARD_GRANT_TABLES = ("app_user", "document", "page", "chunk")

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    # --- tenant --------------------------------------------------------
    op.create_table(
        "tenant",
        sa.Column("id", _UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("clerk_org_id", sa.Text(), nullable=True),
        sa.Column("created_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tenant"),
        sa.UniqueConstraint("slug", name="uq_tenant_slug"),
        sa.UniqueConstraint("clerk_org_id", name="uq_tenant_clerk_org_id"),
    )

    # --- app_user --------------------------------------------------------
    op.create_table(
        "app_user",
        sa.Column("id", _UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("external_auth_id", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_app_user"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], name="fk_app_user_tenant_id_tenant"),
        sa.UniqueConstraint(
            "tenant_id", "external_auth_id", name="uq_app_user_tenant_id_external_auth_id"
        ),
        sa.UniqueConstraint("tenant_id", "email", name="uq_app_user_tenant_id_email"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_app_user_id_tenant_id"),
    )
    op.create_index("ix_app_user_tenant_id", "app_user", ["tenant_id"])

    # --- document --------------------------------------------------------
    op.create_table(
        "document",
        sa.Column("id", _UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("file_type", sa.Text(), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="uploaded", nullable=False),
        sa.Column("source_system", sa.Text(), server_default="upload", nullable=False),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column("source_version", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("synced_at", _TS, nullable=True),
        sa.Column("created_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_document"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], name="fk_document_tenant_id_tenant"),
        sa.UniqueConstraint("tenant_id", "s3_key", name="uq_document_tenant_id_s3_key"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_document_id_tenant_id"),
        sa.CheckConstraint(
            "file_type IN ('pdf', 'docx', 'doc', 'xlsx', 'xls', 'rtf', 'xml', 'other')",
            name="ck_document_file_type_valid",
        ),
        sa.CheckConstraint(
            "status IN ('uploaded', 'queued', 'parsing', 'parsed', 'failed')",
            name="ck_document_status_valid",
        ),
    )
    op.create_index("ix_document_tenant_id", "document", ["tenant_id"])
    op.create_index("ix_document_tenant_id_sha256", "document", ["tenant_id", "sha256"])

    # --- page --------------------------------------------------------
    op.create_table(
        "page",
        sa.Column("id", _UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("document_id", _UUID, nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("render_s3_key", sa.Text(), nullable=True),
        sa.Column("created_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_page"),
        sa.ForeignKeyConstraint(
            ["document_id", "tenant_id"],
            ["document.id", "document.tenant_id"],
            name="fk_page_document_id_document",
        ),
        sa.UniqueConstraint("document_id", "page_no", name="uq_page_document_id_page_no"),
        sa.CheckConstraint(
            "ocr_confidence IS NULL OR ocr_confidence BETWEEN 0 AND 1",
            name="ck_page_ocr_confidence_range",
        ),
    )
    op.create_index("ix_page_tenant_id", "page", ["tenant_id"])

    # --- chunk --------------------------------------------------------
    op.create_table(
        "chunk",
        sa.Column("id", _UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("document_id", _UUID, nullable=False),
        sa.Column("section_path", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("created_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_chunk"),
        sa.ForeignKeyConstraint(
            ["document_id", "tenant_id"],
            ["document.id", "document.tenant_id"],
            name="fk_chunk_document_id_document",
        ),
    )
    op.create_index("ix_chunk_tenant_id", "chunk", ["tenant_id"])
    op.create_index("ix_chunk_document_id_page", "chunk", ["document_id", "page"])

    # --- audit_log --------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", _UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("actor", _UUID, nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_table", sa.Text(), nullable=False),
        sa.Column("target_id", _UUID, nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("prev_hash", sa.Text(), nullable=True),
        sa.Column("hash", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
        sa.ForeignKeyConstraint(
            ["actor", "tenant_id"],
            ["app_user.id", "app_user.tenant_id"],
            name="fk_audit_log_actor_app_user",
        ),
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])
    op.create_index("ix_audit_log_actor", "audit_log", ["actor"])
    op.create_index("ix_audit_log_tenant_id_seq", "audit_log", ["tenant_id", "seq"])
    op.create_index("ix_audit_log_target", "audit_log", ["target_table", "target_id"])

    # --- RLS ---------------------------------------------------------------
    # Autogenerate never produces ENABLE/FORCE ROW LEVEL SECURITY, CREATE
    # POLICY, or GRANT — hand-added here, in the same migration/transaction
    # as the CREATE TABLEs above, so it's structurally impossible (Postgres
    # DDL is transactional) to persist a state where these tables exist
    # without RLS.
    #
    # tenant is the one exception to the standard per-table policy: it has
    # no tenant_id column (its id *is* the tenant identity), and tenant
    # creation necessarily happens before any tenant context exists to scope
    # against, so it gets a permissive INSERT policy alongside a scoped
    # SELECT/UPDATE policy rather than the single USING/WITH CHECK pair
    # every other table gets.
    op.execute("ALTER TABLE tenant ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_self_read_update ON tenant
            FOR SELECT USING (id = current_setting('app.tenant_id', true)::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_self_update ON tenant
            FOR UPDATE
            USING      (id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (id = current_setting('app.tenant_id', true)::uuid)
        """
    )
    op.execute("CREATE POLICY tenant_provision_insert ON tenant FOR INSERT WITH CHECK (true)")
    op.execute("GRANT SELECT, INSERT, UPDATE ON tenant TO eklabs_app")

    for table in _STANDARD_GRANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                USING      (tenant_id = current_setting('app.tenant_id', true)::uuid)
                WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
            """
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO eklabs_app")

    # audit_log: append-only is enforced by grants, not by the hash chain —
    # SELECT, INSERT only, no UPDATE/DELETE granted at all. A fresh role has
    # zero privileges by default, so there is nothing to bypass.
    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON audit_log
            USING      (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT ON audit_log TO eklabs_app")


def downgrade() -> None:
    # Reverse dependency order: children before the parents they FK to.
    op.drop_table("audit_log")
    op.drop_table("chunk")
    op.drop_table("page")
    op.drop_table("document")
    op.drop_table("app_user")
    op.drop_table("tenant")
