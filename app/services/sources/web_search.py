"""
On-demand "search the internet for jobs" connector.

This deliberately does NOT scrape Google or any job board directly -- doing
that yourself breaks the same kind of terms-of-service rules discussed for
LinkedIn/Indeed elsewhere in this codebase, and search engines actively
block it. Instead it uses SerpApi (https://serpapi.com/google-jobs-api), a
paid third-party service that legally queries Google's Jobs results (which
themselves aggregate postings from LinkedIn, Indeed, Glassdoor, company
sites, and more) and returns clean structured JSON. You get "search the
whole internet" coverage without either of you touching a page you're not
allowed to automate.

Requires SERPAPI_KEY in .env. Free tier available at serpapi.com (100
searches/month at time of writing) with paid tiers beyond that.

Unlike the other connectors, this one is NOT part of the daily automatic
fetch -- it's triggered explicitly per search via
POST /api/jobs/search-web, since "search the internet for X" is inherently
a user-initiated, query-driven action rather than a standing daily poll.
"""
from typing import List

import httpx

from app.config import get_settings
from app.models import SourceType
from app.services.sources.base import RawJob


class WebJobSearchConnector:
    source_type = SourceType.web_search

    async def search(
        self, query: str, location: str = "", country: str = "", remote_only: bool = False
    ) -> List[RawJob]:
        settings = get_settings()
        if not settings.serpapi_key:
            raise ValueError(
                "SERPAPI_KEY is not set in .env. Get a free key at https://serpapi.com/ "
                "to enable internet-wide job search."
            )

        search_query = query
        if remote_only and "remote" not in query.lower():
            search_query = f"{query} remote"

        params = {
            "engine": "google_jobs",
            "q": search_query,
            "api_key": settings.serpapi_key,
        }
        if location:
            params["location"] = location
        if country:
            params["gl"] = country.lower()

        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.get("https://serpapi.com/search.json", params=params)
            resp.raise_for_status()
            data = resp.json()

        results: List[RawJob] = []
        for item in data.get("jobs_results", []):
            job_id = item.get("job_id") or f"{item.get('title')}-{item.get('company_name')}"
            description = item.get("description", "")
            location_text = item.get("location", "")

            apply_url = ""
            apply_options = item.get("apply_options") or []
            if apply_options:
                apply_url = apply_options[0].get("link", "")

            results.append(
                RawJob(
                    source=self.source_type,
                    source_job_id=str(job_id),
                    title=item.get("title", ""),
                    company=item.get("company_name", ""),
                    location=location_text,
                    country=country.upper() if country else "",
                    remote="remote" in (item.get("title", "") + description + location_text).lower(),
                    description=description,
                    url=apply_url,
                    salary_text=_extract_salary(item),
                    posted_date=None,
                )
            )
        return results


def _extract_salary(item: dict) -> str:
    for key, value in (item.get("detected_extensions") or {}).items():
        if key == "salary":
            return str(value)
    return ""
