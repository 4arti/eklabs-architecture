from eklabs_platform.evidence.citation_checks import (
    check_citation,
    numbers_units_match,
    quote_exists,
)

SOURCE_TEXT = (
    "The recommended starting dose is 10 mg once daily, increased to a "
    "maximum of 20 mg once daily if tolerated. In clinical trials, 45% of "
    "patients receiving the 10 mg dose achieved the primary endpoint."
)


def test_quote_exists_exact_match_passes() -> None:
    outcome = quote_exists("the recommended starting dose is 10 mg once daily", SOURCE_TEXT)
    assert outcome.verdict == "pass"


def test_quote_exists_near_exact_whitespace_variant_passes() -> None:
    # Extra/odd whitespace — the kind of thing OCR noise introduces —
    # should still count as near-exact.
    outcome = quote_exists("the recommended  starting   dose is 10 mg once daily", SOURCE_TEXT)
    assert outcome.verdict == "pass"


def test_quote_exists_fabricated_sentence_fails() -> None:
    outcome = quote_exists(
        "the drug was withdrawn from the market due to safety concerns", SOURCE_TEXT
    )
    assert outcome.verdict == "fail"


def test_numbers_units_match_when_quote_number_present() -> None:
    outcome = numbers_units_match("the maximum dose is 20 mg once daily", SOURCE_TEXT)
    assert outcome.verdict == "pass"


def test_numbers_units_match_rejects_altered_number() -> None:
    # 10 mg -> 15 mg: a single-digit change that quote_exists' fuzzy
    # matching alone might not catch, since the surrounding sentence is
    # still almost identical.
    outcome = numbers_units_match("the recommended starting dose is 15 mg once daily", SOURCE_TEXT)
    assert outcome.verdict == "fail"
    assert outcome.detail is not None
    missing = outcome.detail["missing"]
    assert isinstance(missing, list)
    assert "15" in missing


def test_numbers_units_match_rejects_altered_percentage() -> None:
    outcome = numbers_units_match(
        "90% of patients receiving the 10 mg dose achieved the primary endpoint", SOURCE_TEXT
    )
    assert outcome.verdict == "fail"


def test_check_citation_real_quote_passes_both_checks() -> None:
    outcomes = check_citation(
        "in clinical trials, 45% of patients receiving the 10 mg dose achieved the primary "
        "endpoint",
        SOURCE_TEXT,
    )
    assert all(o.verdict == "pass" for o in outcomes)


def test_check_citation_altered_number_fails_despite_near_exact_wording() -> None:
    outcomes = check_citation(
        "the recommended starting dose is 15 mg once daily",
        SOURCE_TEXT,
    )
    verdicts = {o.check: o.verdict for o in outcomes}
    # The sentence is close enough wording-wise that quote_exists alone
    # could plausibly pass it — proving numbers_units_match is what
    # actually catches this is the point of the test.
    assert verdicts["numbers_units_match"] == "fail"


def test_check_citation_fabricated_quote_fails_every_check_it_can() -> None:
    outcomes = check_citation(
        "the drug caused severe liver failure in 80% of patients", SOURCE_TEXT
    )
    verdicts = {o.check: o.verdict for o in outcomes}
    assert verdicts["quote_exists"] == "fail"
