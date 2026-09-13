"""
Common interface every job source connector implements. This is what makes
it possible to add a new source later (another ATS board, another
aggregator) without touching the fetch pipeline: just implement
`fetch(profile)` and register the connector in `services/aggregator.py`.

NOTE ON LINKEDIN / INDEED
-------------------------
There is deliberately no LinkedIn or Indeed connector here that logs in and
scrapes/auto-applies. Both platforms:
  - have no public API for an individual to search jobs or submit
    applications on their own behalf, and
  - explicitly prohibit automated scraping / automation of the logged-in
    site in their user agreements; doing it anyway risks account suspension.

Jobs from either platform can still be filtered and tailored by this app:
use POST /api/jobs/manual to paste in the title/company/description/url of
a specific listing you found there. It then flows through the exact same
scoring + tailoring pipeline as everything else -- you just add it by hand
instead of it being auto-fetched.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from app.models import SourceType


@dataclass
class RawJob:
    source: SourceType
    source_job_id: str
    title: str
    company: str
    location: str = ""
    country: str = ""      # ISO country code when the source/connector knows it, else ""
    remote: bool = False
    description: str = ""
    url: str = ""
    salary_text: str = ""
    posted_date: Optional[datetime] = None


class JobSourceConnector(ABC):
    source_type: SourceType

    @abstractmethod
    async def fetch(
        self,
        profile,
        companies: Optional[List[str]] = None,
        countries: Optional[List[str]] = None,
    ) -> List[RawJob]:
        """
        Return the jobs this source currently has for the given profile.

        `companies` is only used by ATS-board connectors (Greenhouse, Lever)
        where the user tracks specific company slugs rather than searching
        by keyword.

        `countries` is a list of ISO country codes from SearchSettings, only
        used by connectors that support country-scoped search (currently
        Adzuna). Connectors that don't support it ignore the argument.
        """
        raise NotImplementedError
