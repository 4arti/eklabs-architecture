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

_REPO_ROOT = Path(__file__).resolve().parent


@pytest.fixture(scope="session", autouse=True)
def _migrated_db() -> None:
    """Runs `alembic upgrade head` once per test session, against
    ALEMBIC_DATABASE_URL (eklabs_migrator), so `pytest` alone reproduces the
    environment — no separate manual migration step for a contributor."""
    config = Config(str(_REPO_ROOT / "alembic.ini"))
    command.upgrade(config, "head")
