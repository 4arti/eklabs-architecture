"""Fails if any file under src/eklabs_platform imports from products.

platform/ (spec.md's name for it; the installed/importable package is named
eklabs_platform, not platform, to avoid colliding with Python's stdlib
`platform` module) is the shared layer and products/ is per-product code
(spec.md S3); it must never depend on a specific product. Enforced here via
AST inspection rather than a text grep so it can't be fooled by a
"products" substring in a comment or string, and isn't fooled by import
aliasing.
"""

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_ROOT = REPO_ROOT / "src" / "eklabs_platform"


def imported_top_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def find_violations() -> list[str]:
    violations = []
    for path in PLATFORM_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if "products" in imported_top_level_names(tree):
            violations.append(str(path.relative_to(REPO_ROOT)))
    return violations


def main() -> int:
    if not PLATFORM_ROOT.exists():
        print(f"nothing to check yet: {PLATFORM_ROOT} does not exist")
        return 0

    violations = find_violations()
    if violations:
        print("platform/ must never import from products/ (CLAUDE.md hard rule):")
        for path in violations:
            print(f"  {path}")
        return 1

    print(
        f"OK: no platform -> products imports ({len(list(PLATFORM_ROOT.rglob('*.py')))} files checked)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
