"""Citation checks 1-2 (spec.md §6/§7) — plain code, no AI, run before a
human ever sees a draft. Checks 3 (support) and 4 (consistency) need an AI
judgment call and a cross-section fact store; they wait for Phase 3.

No `check_result` table yet — see the ingestion-pipeline plan's Context
section for why `claim`/`citation`/`check_result`/`run` are deliberately
deferred until the agent runtime (Phase 3) has a real producer for them.
`CheckOutcome`'s fields already match that future row shape, so wiring this
to a table later is a persistence change, not a redesign.
"""

import re

from pydantic import BaseModel
from rapidfuzz import fuzz

# Below this score (rapidfuzz's partial_ratio, 0-100), a quote doesn't count
# as "near-exact" — chosen to tolerate minor OCR noise/whitespace drift, not
# to paper over a materially different sentence.
_NEAR_EXACT_THRESHOLD = 90.0

# The %-suffix is wrapped together with its leading whitespace in ONE
# optional group — `\d+(?:[.,]\d+)*\s*%?` (whitespace and % independently
# optional) looks equivalent but isn't: `\s*` alone is already satisfied by
# zero characters, so it never actually forces `%?` to also match, yet
# still greedily eats any real trailing whitespace into the match (e.g.
# "15 mg" wrongly matches "15 ", not "15"). Keeping them as one atomic
# group means the whitespace is only consumed when a literal % follows it.
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*(?:\s*%)?")


class CheckOutcome(BaseModel):
    check: str
    verdict: str  # "pass" | "fail"
    detail: dict[str, object] | None = None


def _normalize(text: str) -> str:
    return " ".join(text.split())


def quote_exists(quote: str, source_text: str) -> CheckOutcome:
    """Check 1: the quote exists in the source, exact or near-exact — a
    sentence that fails this is dropped outright (spec §7)."""
    normalized_quote = _normalize(quote)
    normalized_source = _normalize(source_text)

    if normalized_quote in normalized_source:
        return CheckOutcome(check="quote_exists", verdict="pass", detail={"match": "exact"})

    score = fuzz.partial_ratio(normalized_quote, normalized_source)
    if score >= _NEAR_EXACT_THRESHOLD:
        return CheckOutcome(
            check="quote_exists", verdict="pass", detail={"match": "near_exact", "score": score}
        )
    return CheckOutcome(
        check="quote_exists", verdict="fail", detail={"match": "none", "score": score}
    )


def numbers_units_match(quote: str, source_text: str) -> CheckOutcome:
    """Check 2: every number (and attached %) in the quote must appear in
    the source — catches an altered figure even when the surrounding prose
    still reads as a near-exact match."""
    quote_numbers = _NUMBER_RE.findall(_normalize(quote))
    source_numbers = set(_NUMBER_RE.findall(_normalize(source_text)))

    missing = [n for n in quote_numbers if n not in source_numbers]
    if missing:
        return CheckOutcome(
            check="numbers_units_match",
            verdict="fail",
            detail={"missing": missing, "quote_numbers": quote_numbers},
        )
    return CheckOutcome(
        check="numbers_units_match", verdict="pass", detail={"quote_numbers": quote_numbers}
    )


def check_citation(quote: str, source_text: str) -> list[CheckOutcome]:
    """Runs both mechanical checks. A sentence is citable only if every
    outcome here is a pass — the caller (eventually the drafter) decides
    what "drop the sentence" means for its own flow; this module only judges."""
    return [quote_exists(quote, source_text), numbers_units_match(quote, source_text)]
