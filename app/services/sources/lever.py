"""
Lever public postings API connector.
Docs: https://github.com/lever/postings-api

No API key needed:

    https://api.lever.co/v0/postings/{company-slug}?mode=json

The slug is the bit in the company's public jobs URL, e.g.
jobs.lever.co/netflix -> slug "netflix".
"""
import re
from typing import List, Optional

import httpx

from app.models import SourceType
from app.services.sources.base import JobSourceConnector, RawJob

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    return _TAG_RE.sub(" ", html or "").replace("&nbsp;", " ").strip()


class LeverConnector(JobSourceConnector):
    source_type = SourceType.lever

    async def fetch(
        self, profile, companies: Optional[List[str]] = None, countries: Optional[List[str]] = None
    ) -> List[RawJob]:
        if not companies:
            return []

        results: List[RawJob] = []
        async with httpx.AsyncClient(timeout=20) as client:
            for slug in companies:
                url = f"https://api.lever.co/v0/postings/{slug}"
                try:
                    resp = await client.get(url, params={"mode": "json"})
                    resp.raise_for_status()
                except httpx.HTTPStatusError:
                    continue

                for item in resp.json():
                    categories = item.get("categories", {}) or {}
                    location = categories.get("location", "") or ""
                    description = _strip_html(item.get("descriptionPlain") or item.get("description", ""))
                    results.append(
                        RawJob(
                            source=self.source_type,
                            source_job_id=str(item.get("id")),
                            title=item.get("text", ""),
                            company=slug,
                            location=location,
                            remote="remote" in location.lower(),
                            description=description,
                            url=item.get("hostedUrl", ""),
                            salary_text="",
                            posted_date=None,
                        )
                    )
        return results
