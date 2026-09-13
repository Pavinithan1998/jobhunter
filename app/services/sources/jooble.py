"""
Jooble job search API connector.
Docs: https://jooble.org/api/about

Requires JOOBLE_API_KEY in .env (free key at https://jooble.org/api/about).
Jooble's API is POST-based with the key in the URL path.
"""
from typing import List, Optional

import httpx

from app.config import get_settings
from app.models import SourceType
from app.services.sources.base import JobSourceConnector, RawJob


class JoobleConnector(JobSourceConnector):
    source_type = SourceType.jooble

    async def fetch(
        self, profile, companies: Optional[List[str]] = None, countries: Optional[List[str]] = None
    ) -> List[RawJob]:
        settings = get_settings()
        if not settings.jooble_api_key:
            return []

        titles = [t.strip() for t in profile.target_titles.split(",") if t.strip()] or [""]
        locations = [l.strip() for l in profile.target_locations.split(",") if l.strip()] or [""]

        results: List[RawJob] = []
        url = f"https://jooble.org/api/{settings.jooble_api_key}"

        async with httpx.AsyncClient(timeout=20) as client:
            for title in titles:
                for location in locations:
                    payload = {"keywords": title, "location": location}
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                    for item in data.get("jobs", []):
                        job_id = item.get("id") or item.get("link", "")
                        results.append(
                            RawJob(
                                source=self.source_type,
                                source_job_id=str(job_id),
                                title=item.get("title", ""),
                                company=item.get("company", ""),
                                location=item.get("location", ""),
                                remote="remote" in (item.get("title", "") + item.get("snippet", "")).lower(),
                                description=item.get("snippet", ""),
                                url=item.get("link", ""),
                                salary_text=item.get("salary", "") or "",
                                posted_date=None,
                            )
                        )
        return results
