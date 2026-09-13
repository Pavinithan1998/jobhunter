"""
Checks a company against the UK Home Office's public register of licensed
Worker and Temporary Worker sponsors -- i.e. whether they currently hold a
sponsor licence at all, which is a stronger, independently-verifiable
signal than guessing from a job description's wording (see
services/sponsorship.py for that separate, description-text heuristic).

Source: https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers
This is a public CSV the Home Office republishes regularly. gov.uk doesn't
expose it as a stable API -- the actual file is a dated attachment linked
from that publication page -- so `refresh()` fetches the page, finds the
current ".csv" link, and downloads that. If gov.uk ever restructures the
page and auto-discovery breaks, set UK_SPONSOR_REGISTER_CSV_URL in .env to
the current direct link as a manual override.

This module never runs automatically on every request: call
POST /api/sources/uk-sponsor-register/refresh periodically (weekly is
plenty, since the register itself only updates every few days) to
(re)download it. Lookups (`is_licensed`) read the local cached copy in
storage/, so they're instant and need no network call.

Being ABSENT from the register is a genuine negative signal (it means the
company does not currently hold a Worker/Temporary Worker sponsor licence),
but a name-matching miss is also possible for large/multi-entity employers
that sponsor under a different registered legal name than their trading
name -- treat a "False" result as "not found under this name", not an
absolute guarantee, and the reasoning string says so.
"""
import csv
import difflib
import json
import re
from typing import Optional, Tuple

import httpx

from app.config import STORAGE_DIR, get_settings
from app.utils.time import utcnow

PUBLICATION_PAGE_URL = "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
CACHE_CSV_PATH = STORAGE_DIR / "uk_sponsor_register.csv"
META_PATH = STORAGE_DIR / "uk_sponsor_register_meta.json"

_SUFFIX_RE = re.compile(r"\b(ltd|limited|plc|llp|llc|inc|incorporated|corp|corporation|co|company|group)\b")
_PUNCT_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")

# In-memory cache of the parsed register, rebuilt only when the cache file
# on disk changes (checked via mtime) -- so repeated lookups during a batch
# scoring run don't re-parse the CSV every time.
_cache_mtime: Optional[float] = None
_normalized_names: set = set()
_by_first_word: dict = {}


def _normalize(name: str) -> str:
    n = (name or "").lower()
    n = _PUNCT_RE.sub(" ", n)
    n = _SUFFIX_RE.sub(" ", n)
    n = _WHITESPACE_RE.sub(" ", n).strip()
    return n


def _load_cache_if_needed() -> bool:
    """Returns True if a usable cache is loaded in memory, False if no cache file exists yet."""
    global _cache_mtime, _normalized_names, _by_first_word

    if not CACHE_CSV_PATH.exists():
        return False

    mtime = CACHE_CSV_PATH.stat().st_mtime
    if _cache_mtime == mtime and _normalized_names:
        return True  # already loaded, file hasn't changed

    names = set()
    buckets: dict = {}
    with CACHE_CSV_PATH.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        name_field = None
        for field in reader.fieldnames or []:
            if "organisation" in field.lower() or "organization" in field.lower():
                name_field = field
                break
        name_field = name_field or (reader.fieldnames[0] if reader.fieldnames else None)

        if name_field:
            for row in reader:
                normalized = _normalize(row.get(name_field, ""))
                if not normalized:
                    continue
                names.add(normalized)
                first_word = normalized.split(" ")[0]
                buckets.setdefault(first_word, []).append(normalized)

    _normalized_names = names
    _by_first_word = buckets
    _cache_mtime = mtime
    return True


def is_licensed(company_name: str) -> Tuple[Optional[bool], str]:
    """
    Returns (True/False/None, reasoning). None means "not checked" --
    either the register hasn't been downloaded yet, or the company name was
    unusable for matching.
    """
    if not _load_cache_if_needed():
        return None, (
            "UK sponsor register hasn't been downloaded yet -- "
            "POST /api/sources/uk-sponsor-register/refresh to fetch it."
        )

    normalized = _normalize(company_name)
    if not normalized:
        return None, "Company name was empty or unusable for matching."

    if normalized in _normalized_names:
        return True, "Exact name match found in the current UK Home Office sponsor register."

    first_word = normalized.split(" ")[0]
    candidates = _by_first_word.get(first_word, [])
    close = difflib.get_close_matches(normalized, candidates, n=1, cutoff=0.85) if candidates else []
    if close:
        return True, f"Close name match found in the UK sponsor register (matched as '{close[0]}')."

    return False, (
        "No match found in the current UK Home Office sponsor register under this name. "
        "This means they don't currently hold a Worker/Temporary Worker sponsor licence under "
        "this exact registered name -- worth double-checking directly if the match matters to you."
    )


async def refresh() -> dict:
    """
    Downloads the current register CSV (or re-checks the manual override
    URL) and rebuilds the local cache. Safe to call repeatedly -- each call
    fully replaces the cached file.
    """
    settings = get_settings()
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        if settings.uk_sponsor_register_csv_url:
            csv_url = settings.uk_sponsor_register_csv_url
        else:
            page_resp = await client.get(PUBLICATION_PAGE_URL)
            page_resp.raise_for_status()
            match = re.search(r'href="([^"]+\.csv)"', page_resp.text, re.IGNORECASE)
            if not match:
                raise ValueError(
                    "Couldn't find a CSV link on the gov.uk register page -- it may have been "
                    "restructured. Set UK_SPONSOR_REGISTER_CSV_URL in .env to the current direct "
                    "CSV link as a manual override (find it at "
                    f"{PUBLICATION_PAGE_URL})."
                )
            csv_url = match.group(1)
            if csv_url.startswith("/"):
                csv_url = f"https://www.gov.uk{csv_url}"

        csv_resp = await client.get(csv_url)
        csv_resp.raise_for_status()

    CACHE_CSV_PATH.write_bytes(csv_resp.content)

    # Force a reload on next lookup and count records now for the status response.
    global _cache_mtime
    _cache_mtime = None
    _load_cache_if_needed()

    meta = {
        "source_url": csv_url,
        "refreshed_at": utcnow().isoformat(),
        "record_count": len(_normalized_names),
    }
    META_PATH.write_text(json.dumps(meta), encoding="utf-8")
    return meta


def get_status() -> dict:
    if not META_PATH.exists():
        return {"downloaded": False, "record_count": 0, "refreshed_at": None, "source_url": None}
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    return {"downloaded": True, **meta}
