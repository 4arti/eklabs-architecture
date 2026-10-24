"""table_extract

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "table_extract",
        sa.Column("id", _UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("document_id", _UUID, nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("cells", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_table_extract"),
        sa.ForeignKeyConstraint(
            ["document_id", "tenant_id"],
            ["document.id", "document.tenant_id"],
            name="fk_table_extract_document_id_document",
        ),
    )
    op.create_index("ix_table_extract_tenant_id", "table_extract", ["tenant_id"])
    op.create_index(
        "ix_table_extract_document_id_page_no", "table_extract", ["document_id", "page_no"]
    )

    # --- RLS ---------------------------------------------------------------
    # Same pattern as 0002/0003: ENABLE/FORCE + a single tenant_isolation
    # policy + GRANT SELECT, INSERT, UPDATE, in the same migration/transaction
    # as the CREATE TABLE above.
    op.execute("ALTER TABLE table_extract ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE table_extract FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON table_extract
            USING      (tenant_id = current_setting('app.tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON table_extract TO eklabs_app")


def downgrade() -> None:
    op.drop_table("table_extract")
