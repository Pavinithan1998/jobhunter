"""
A fast, free, keyword-based first guess at whether a job is likely to
sponsor a work visa. Runs on every job the moment it's fetched, so the
signal exists even before (or without) an LLM scoring pass.

This is deliberately a heuristic, not a certainty -- job descriptions are
inconsistent about mentioning sponsorship at all. `score_job` in
matching.py refines this with an LLM read of the full description when
scoring runs, which is the more reliable signal; treat this module's
output as a reasonable default, not the final word.
"""
import re

from app.models import SponsorshipStatus

_UNLIKELY_PATTERNS = [
    r"\bno\s+(visa\s+)?sponsorship\b",
    r"\bunable to (offer|provide) (visa )?sponsorship\b",
    r"\bunable to sponsor\b",
    r"\bnot able to sponsor\b",
    r"\bcannot sponsor\b",
    r"\bwe do not sponsor\b",
    r"\bmust (already )?have (the )?right to work\b",
    r"\bmust have valid work authori[sz]ation\b",
    r"\bno visa support\b",
    r"\bplease do not apply.{0,30}sponsorship\b",
]

_LIKELY_PATTERNS = [
    r"\bvisa sponsorship (is )?available\b",
    r"\bwe (will|can|are able to) sponsor\b",
    r"\bsponsorship (is )?offered\b",
    r"\bsponsorship provided\b",
    r"\bwill sponsor (a )?visa\b",
    r"\bskilled worker visa\b.{0,40}\bsponsor\b",
    r"\blicensed sponsor\b",
]


def classify(description: str) -> tuple[SponsorshipStatus, str]:
    text = (description or "").lower()

    for pattern in _UNLIKELY_PATTERNS:
        if re.search(pattern, text):
            return (
                SponsorshipStatus.unlikely,
                "Job description contains language suggesting sponsorship isn't offered "
                "(keyword match, not yet confirmed by full-text review).",
            )

    for pattern in _LIKELY_PATTERNS:
        if re.search(pattern, text):
            return (
                SponsorshipStatus.likely,
                "Job description explicitly mentions visa sponsorship "
                "(keyword match, not yet confirmed by full-text review).",
            )

    return (
        SponsorshipStatus.unclear,
        "Sponsorship isn't mentioned either way in the listing -- run relevance "
        "scoring for a closer LLM read, or check directly with the employer.",
    )
