"""Spec §5's FormatPolicy — named format_policy() here (snake_case, matching
every other function in this codebase, e.g. record_event, tenant_scoped_session)
rather than spec's literal capitalized name.

Answers one question: which formats are allowed for this authority,
application type and situation, and why? The wizard, the API and the
publisher are all meant to ask this before creating anything — today,
applications.py::create_application() is the one place that actually does,
which is what makes "an invalid combination can't be created anywhere" true
even before those other callers exist.
"""

from datetime import date

from pydantic import BaseModel

from products.ectd.profiles.loader import AuthorityProfile, load_profile


class FormatDecision(BaseModel):
    format: str
    allowed: bool
    reason: str
    since: date | None = None


class FormatPolicyResult(BaseModel):
    authority: str
    app_type: str
    situation: str
    app_type_valid: bool
    decisions: list[FormatDecision]

    def is_allowed(self, format: str) -> bool:
        return any(d.format == format and d.allowed for d in self.decisions)

    def allowed_formats(self) -> list[str]:
        return [d.format for d in self.decisions if d.allowed]

    def reason_for(self, format: str) -> str | None:
        return next((d.reason for d in self.decisions if d.format == format), None)

    def decision_for(self, format: str) -> FormatDecision | None:
        return next((d for d in self.decisions if d.format == format), None)


class InvalidFormatCombinationError(ValueError):
    """Raised by validate_application_format() — the enforcement chokepoint."""


def _decide_one_format(
    profile: AuthorityProfile,
    format_name: str,
    situation: str,
    app_type: str,
    app_type_valid: bool,
) -> FormatDecision:
    if not app_type_valid:
        return FormatDecision(
            format=format_name,
            allowed=False,
            reason=(
                f"{app_type!r} is not a recognized application type for "
                f"{profile.authority} — expected one of {profile.application_types!r}"
            ),
        )

    rule = profile.formats[format_name]
    allowed = situation in rule.allowed_for
    if rule.reason:
        reason = rule.reason
    elif allowed:
        reason = f"allowed for {situation}" + (f" since {rule.since}" if rule.since else "")
    else:
        reason = f"not allowed for {situation}"
    return FormatDecision(format=format_name, allowed=allowed, reason=reason, since=rule.since)


def format_policy(authority: str, app_type: str, situation: str) -> FormatPolicyResult:
    """Two independent checks, not one:
      1. is app_type in profile.application_types (authority-valid app type at all)?
      2. per format: is situation in formats[format].allowed_for (format-valid for this situation)?
    If (1) is false, every format is reported not-allowed, naming the bad
    app_type, regardless of (2) — an unrecognized application type makes
    every format decision moot.
    """
    profile = load_profile(authority)
    app_type_valid = app_type in profile.application_types
    decisions = [
        _decide_one_format(profile, name, situation, app_type, app_type_valid)
        for name in profile.formats
    ]
    return FormatPolicyResult(
        authority=authority,
        app_type=app_type,
        situation=situation,
        app_type_valid=app_type_valid,
        decisions=decisions,
    )


def validate_application_format(
    authority: str, app_type: str, format: str, situation: str
) -> FormatPolicyResult:
    """The enforcement chokepoint. Raises InvalidFormatCombinationError if
    the combination isn't allowed; returns the full result otherwise."""
    result = format_policy(authority, app_type, situation)
    if not result.is_allowed(format):
        reason = (
            result.reason_for(format) or f"{format!r} is not a recognized format for {authority}"
        )
        raise InvalidFormatCombinationError(
            f"{format} is not allowed for authority={authority!r} "
            f"app_type={app_type!r} situation={situation!r}: {reason}"
        )
    return result
