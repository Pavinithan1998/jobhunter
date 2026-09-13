"""
Adzuna job search API connector.
Docs: https://developer.adzuna.com/overview

Requires ADZUNA_APP_ID and ADZUNA_APP_KEY in .env (free tier available at
https://developer.adzuna.com/). If either is missing, `fetch` returns an
empty list rather than raising, so the rest of the pipeline still runs.

Country selection: Adzuna's API is scoped to one country per request (it's
part of the URL path), so this connector queries once per country in
`countries` (from SearchSettings.target_countries). Falls back to the
single ADZUNA_COUNTRY env default if no countries are configured yet.
Adzuna only covers a fixed set of countries (gb, us, au, ca, de, fr, in,
it, nl, pl, ru, sg, za, mx, br, nz, at, ...) -- an unsupported code is
skipped rather than failing the whole fetch.
"""
from datetime import datetime
from typing import List, Optional

import httpx

from app.config import get_settings
from app.models import SourceType
from app.services.sources.base import JobSourceConnector, RawJob


class AdzunaConnector(JobSourceConnector):
    source_type = SourceType.adzuna

    async def fetch(
        self, profile, companies: Optional[List[str]] = None, countries: Optional[List[str]] = None
    ) -> List[RawJob]:
        settings = get_settings()
        if not settings.adzuna_app_id or not settings.adzuna_app_key:
            return []

        titles = [t.strip() for t in profile.target_titles.split(",") if t.strip()] or [""]
        country_codes = [c.strip().lower() for c in (countries or []) if c.strip()] or [settings.adzuna_country]

        results: List[RawJob] = []

        async with httpx.AsyncClient(timeout=20) as client:
            for country_code in country_codes:
                for title in titles:
                    url = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1"
                    params = {
                        "app_id": settings.adzuna_app_id,
                        "app_key": settings.adzuna_app_key,
                        "results_per_page": 50,
                        "what": title,
                        "content-type": "application/json",
                    }
                    if profile.remote_preference == "remote":
                        params["what"] = f"{title} remote"

                    try:
                        resp = await client.get(url, params=params)
                        resp.raise_for_status()
                    except httpx.HTTPStatusError:
                        continue  # country not supported by Adzuna, or a transient error -- skip it
                    data = resp.json()

                    for item in data.get("results", []):
                        posted = None
                        if item.get("created"):
                            try:
                                posted = datetime.fromisoformat(item["created"].replace("Z", "+00:00"))
                            except ValueError:
                                posted = None

                        results.append(
                            RawJob(
                                source=self.source_type,
                                source_job_id=str(item.get("id")),
                                title=item.get("title", ""),
                                company=(item.get("company") or {}).get("display_name", ""),
                                location=(item.get("location") or {}).get("display_name", ""),
                                country=country_code.upper(),
                                remote="remote" in (item.get("title", "") + item.get("description", "")).lower(),
                                description=item.get("description", ""),
                                url=item.get("redirect_url", ""),
                                salary_text=_salary_text(item),
                                posted_date=posted,
                            )
                        )
        return results


def _salary_text(item: dict) -> str:
    lo, hi = item.get("salary_min"), item.get("salary_max")
    if not lo and not hi:
        return ""
    if lo and hi and lo != hi:
        return f"{int(lo):,} - {int(hi):,}"
    return f"{int(lo or hi):,}"
