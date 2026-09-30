"""ectd product tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same shape as 0002: SELECT, INSERT, UPDATE only — no DELETE anywhere in
# this data model.
_TABLES = ("product", "application", "section")

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    # --- product --------------------------------------------------------
    op.create_table(
        "product",
        sa.Column("id", _UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("inn", sa.Text(), nullable=True),
        sa.Column("dosage_form", sa.Text(), nullable=False),
        sa.Column("strength", sa.Text(), nullable=False),
        sa.Column("product_class", sa.Text(), nullable=False),
        sa.Column("created_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_product"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], name="fk_product_tenant_id_tenant"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_product_id_tenant_id"),
        sa.CheckConstraint(
            "product_class IN ('small_molecule', 'biologic')",
            name="ck_product_product_class_valid",
        ),
    )
    op.create_index("ix_product_tenant_id", "product", ["tenant_id"])

    # --- application --------------------------------------------------------
    op.create_table(
        "application",
        sa.Column("id", _UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("product_id", _UUID, nullable=False),
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("app_type", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("profile_version", sa.Text(), nullable=False),
        sa.Column("app_number", sa.Text(), nullable=True),
        sa.Column("created_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_application"),
        sa.ForeignKeyConstraint(
            ["product_id", "tenant_id"],
            ["product.id", "product.tenant_id"],
            name="fk_application_product_id_product",
        ),
        sa.UniqueConstraint("id", "tenant_id", name="uq_application_id_tenant_id"),
        sa.CheckConstraint(
            "format IN ('ctd_pdf', 'ectd_3_2_2', 'ectd_4_0')",
            name="ck_application_format_valid",
        ),
    )
    op.create_index("ix_application_tenant_id", "application", ["tenant_id"])
    op.create_index(
        "ix_application_tenant_id_product_id", "application", ["tenant_id", "product_id"]
    )

    # --- section --------------------------------------------------------
    op.create_table(
        "section",
        sa.Column("id", _UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("application_id", _UUID, nullable=False),
        sa.Column("ctd_code", sa.Text(), nullable=False),
        sa.Column("template_version", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="empty", nullable=False),
        sa.Column("created_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_section"),
        sa.ForeignKeyConstraint(
            ["application_id", "tenant_id"],
            ["application.id", "application.tenant_id"],
            name="fk_section_application_id_application",
        ),
        sa.UniqueConstraint("id", "tenant_id", name="uq_section_id_tenant_id"),
        sa.UniqueConstraint(
            "application_id", "ctd_code", name="uq_section_application_id_ctd_code"
        ),
        sa.CheckConstraint(
            "status IN ('empty', 'drafting', 'in_review', 'approved')",
            name="ck_section_status_valid",
        ),
    )
    op.create_index("ix_section_tenant_id", "section", ["tenant_id"])

    # --- RLS ---------------------------------------------------------------
    # Same pattern as 0002: ENABLE/FORCE + a single tenant_isolation policy
    # + GRANT SELECT, INSERT, UPDATE, in the same migration/transaction as
    # the CREATE TABLEs above, so it's structurally impossible to persist
    # these tables without RLS. No exceptions like tenant's dual-policy
    # design this time — all three are ordinary tenant_id-scoped tables.
    for table in _TABLES:
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


def downgrade() -> None:
    # Reverse dependency order: children before the parents they FK to.
    op.drop_table("section")
    op.drop_table("application")
    op.drop_table("product")
