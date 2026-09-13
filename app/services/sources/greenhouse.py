"""
Greenhouse public job-board API connector.
Docs: https://developers.greenhouse.io/job-board.html

No API key needed -- every company using Greenhouse for hiring exposes a
public read-only feed at:

    https://boards-api.greenhouse.io/v1/boards/{company-slug}/jobs?content=true

The user adds the company slugs they want tracked via
POST /api/sources/greenhouse (the slug is the bit in the company's public
careers URL, e.g. boards.greenhouse.io/stripe -> slug "stripe").
"""
import re
from typing import List, Optional

import httpx

from app.models import SourceType
from app.services.sources.base import JobSourceConnector, RawJob

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    return _TAG_RE.sub(" ", html or "").replace("&nbsp;", " ").strip()


class GreenhouseConnector(JobSourceConnector):
    source_type = SourceType.greenhouse

    async def fetch(
        self, profile, companies: Optional[List[str]] = None, countries: Optional[List[str]] = None
    ) -> List[RawJob]:
        if not companies:
            return []

        results: List[RawJob] = []
        async with httpx.AsyncClient(timeout=20) as client:
            for slug in companies:
                url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
                try:
                    resp = await client.get(url, params={"content": "true"})
                    resp.raise_for_status()
                except httpx.HTTPStatusError:
                    continue  # unknown/misspelled slug -- skip, don't fail the whole fetch

                data = resp.json()
                for item in data.get("jobs", []):
                    location = (item.get("location") or {}).get("name", "")
                    description = _strip_html(item.get("content", ""))
                    results.append(
                        RawJob(
                            source=self.source_type,
                            source_job_id=str(item.get("id")),
                            title=item.get("title", ""),
                            company=slug,
                            location=location,
                            remote="remote" in location.lower() or "remote" in description.lower(),
                            description=description,
                            url=item.get("absolute_url", ""),
                            salary_text="",
                            posted_date=None,
                        )
                    )
        return results
