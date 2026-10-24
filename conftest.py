"""Root-level so pytest's conftest inheritance (directory-tree-based, not
package-based) picks this up for every test in the repo — including
src/products/ectd/tests/, which isn't a descendant of
src/eklabs_platform/core/tests/ and so can't inherit a fixture defined
there. Only _migrated_db lives here; make_tenant and the platform row
factories stay platform-specific in eklabs_platform's own conftest.py.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent

# Module-level, not inside a fixture: pytest imports every test module
# during collection, before any fixture runs — and those imports include
# core/db/session.py's module-level `engine = create_async_engine(...)`,
# which reads APP_DATABASE_URL at import time. A load_dotenv() call placed
# inside _migrated_db would run too late to help; this is the earliest
# point in the whole test session (root conftest.py loads before
# collecting anything) that can still populate os.environ in time.
load_dotenv(_REPO_ROOT / ".env")


@pytest.fixture(scope="session", autouse=True)
def _migrated_db() -> None:
    """Runs `alembic upgrade head` once per test session, against
    ALEMBIC_DATABASE_URL (eklabs_migrator), so `pytest` alone reproduces the
    environment — no separate manual migration step for a contributor."""
    config = Config(str(_REPO_ROOT / "alembic.ini"))
    command.upgrade(config, "head")
