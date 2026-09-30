from datetime import date

import pytest

from products.ectd.format_policy import format_policy
from products.ectd.profiles.loader import (
    ProfileNotFoundError,
    _clear_profile_cache,
    load_profile,
)

US_APPLICATION_TYPES = ["nda_505b1", "nda_505b2", "anda", "bla_351a", "bla_351k"]


def test_ectd_4_0_allowed_for_new_application() -> None:
    result = format_policy("US-FDA", "nda_505b1", "new_application")
    decision = result.decision_for("ectd_4_0")
    assert decision is not None
    assert decision.allowed is True
    assert decision.since == date(2024, 9, 16)


def test_ectd_3_2_2_allowed_for_both_situations() -> None:
    for situation in ("new_application", "existing_3_2_2_application"):
        result = format_policy("US-FDA", "nda_505b1", situation)
        assert result.is_allowed("ectd_3_2_2") is True


def test_ctd_pdf_never_allowed_with_literal_yaml_reason() -> None:
    for situation in ("new_application", "existing_3_2_2_application"):
        result = format_policy("US-FDA", "nda_505b1", situation)
        decision = result.decision_for("ctd_pdf")
        assert decision is not None
        assert decision.allowed is False
        assert decision.reason == "eCTD required for NDA, ANDA, BLA, commercial IND"


def test_unknown_app_type_rejects_every_format_naming_the_bad_type() -> None:
    result = format_policy("US-FDA", "not_a_real_app_type", "new_application")
    assert result.app_type_valid is False
    assert result.allowed_formats() == []
    for decision in result.decisions:
        assert decision.allowed is False
        assert "not_a_real_app_type" in decision.reason or "application_types" in decision.reason


@pytest.mark.parametrize("app_type", US_APPLICATION_TYPES)
def test_all_us_application_types_are_valid(app_type: str) -> None:
    result = format_policy("US-FDA", app_type, "new_application")
    assert result.app_type_valid is True


def test_ectd_4_0_not_allowed_for_existing_3_2_2_application_with_generated_reason() -> None:
    result = format_policy("US-FDA", "nda_505b1", "existing_3_2_2_application")
    decision = result.decision_for("ectd_4_0")
    assert decision is not None
    assert decision.allowed is False
    # ectd_4_0 has no explicit `reason` in the YAML, so this proves the
    # generated-reason fallback path, not just the literal-reason path
    # ctd_pdf already covers.
    assert "not allowed for existing_3_2_2_application" == decision.reason


def test_unknown_authority_raises_profile_not_found() -> None:
    with pytest.raises(ProfileNotFoundError):
        load_profile("EU-EMA")


def test_profile_cache_identity_and_reset() -> None:
    _clear_profile_cache()
    first = load_profile("US-FDA")
    second = load_profile("US-FDA")
    assert first is second
    _clear_profile_cache()
    third = load_profile("US-FDA")
    assert third is not first
