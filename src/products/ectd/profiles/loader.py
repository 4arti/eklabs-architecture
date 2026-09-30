"""Loads one YAML profile per authority (spec §5) — everything that differs
by country: allowed formats and dates, application types, Module 1
structure. format_policy.py is the only thing that should read these
values to make a decision; other code should go through that module, not
parse a profile directly.
"""

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel

_PROFILES_DIR = Path(__file__).resolve().parent


class ProfileNotFoundError(LookupError):
    """Raised when no profile YAML exists for the requested authority."""


class FormatRule(BaseModel):
    # Situations this format is allowed for, e.g. "new_application",
    # "existing_3_2_2_application". Empty list means never allowed.
    allowed_for: list[str] = []
    since: date | None = None
    reason: str | None = None


class AuthorityProfile(BaseModel):
    authority: str
    # Not in spec §5's illustrative YAML — added because application.
    # profile_version (spec §4) needs something to pin to. A schema
    # decision, not a regulatory fact, so it needs no docs/reference/
    # citation.
    version: str
    formats: dict[str, FormatRule]
    application_types: list[str]
    module1: str


def _slug(authority: str) -> str:
    return authority.lower().replace("-", "_")


_cache: dict[str, AuthorityProfile] = {}


def load_profile(authority: str) -> AuthorityProfile:
    """'US-FDA' -> profiles/us_fda.yaml. Cached in-process — the YAML only
    changes via a new deploy, not per-request."""
    if authority in _cache:
        return _cache[authority]

    path = _PROFILES_DIR / f"{_slug(authority)}.yaml"
    if not path.exists():
        raise ProfileNotFoundError(f"no profile for authority {authority!r} at {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    profile = AuthorityProfile.model_validate(data)
    _cache[authority] = profile
    return profile


def _clear_profile_cache() -> None:
    """Test-only: resets the in-process cache between test cases."""
    _cache.clear()
