"""extensions

Revision ID: 0001
Revises:
Create Date: 2026-09-27

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Separate from 0002 deliberately: extension creation is
    # permission-sensitive on managed Postgres (Supabase), so a failure here
    # is immediately diagnosable rather than buried in a large migration.
    # WITH SCHEMA extensions matches Supabase's own convention of keeping
    # extensions out of public; its default search_path already includes
    # extensions, so the `vector` type resolves without further changes.
    op.execute("CREATE SCHEMA IF NOT EXISTS extensions")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
