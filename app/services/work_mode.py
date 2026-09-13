"""
A fast, free, keyword-based guess at whether a job is remote, hybrid, or
onsite, from its title/location/description text plus whatever boolean
"remote" flag the source connector reported. Runs the moment a job is
fetched, same pattern as sponsorship.py.

This is a heuristic, not a certainty: not every listing states its work
mode clearly. Jobs classified `unclear` are NOT auto-dismissed by a
work_mode filter in Settings, on the assumption that excluding a possible
match on an uncertain heuristic is worse than showing one extra job.
"""
import re

from app.models import WorkMode

_HYBRID_PATTERNS = [r"\bhybrid\b"]
_REMOTE_PATTERNS = [r"\bremote\b", r"\bwork from home\b", r"\bwfh\b", r"\bfully distributed\b"]
_ONSITE_PATTERNS = [
    r"\bon[\s-]?site\b",
    r"\bin[\s-]?office\b",
    r"\bin person\b",
    r"\b5 days? (a|per) week in\b",
    r"\bmust be based in\b",
]


def classify(title: str, location: str, description: str, remote_flag: bool = False) -> WorkMode:
    text = f"{title} {location} {description}".lower()

    is_hybrid = any(re.search(p, text) for p in _HYBRID_PATTERNS)
    is_remote = remote_flag or any(re.search(p, text) for p in _REMOTE_PATTERNS)
    is_onsite = any(re.search(p, text) for p in _ONSITE_PATTERNS)

    # Hybrid mentions win even if "remote" also appears (e.g. "remote-friendly hybrid role")
    if is_hybrid:
        return WorkMode.hybrid
    if is_remote:
        return WorkMode.remote
    if is_onsite:
        return WorkMode.onsite
    return WorkMode.unclear
