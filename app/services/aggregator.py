"""
Runs every configured job source connector, de-duplicates against what's
already in the database, and stores genuinely new listings.

`store_raw_jobs` is also reused by the on-demand web-search endpoint
(app/routers/jobs.py) so both paths get the same de-duplication,
work-mode classification, sponsorship-heuristic, and UK-register-lookup
treatment.
"""
import logging
from typing import List, Optional, Tuple

from sqlmodel import Session, select

from app.models import JobListing, JobStatus, Profile, SearchSettings, SourceType, TrackedCompany
from app.schemas import FetchResult
from app.services import sponsorship, uk_sponsor_register, work_mode
from app.services.sources.adzuna import AdzunaConnector
from app.services.sources.base import RawJob
from app.services.sources.greenhouse import GreenhouseConnector
from app.services.sources.jooble import JoobleConnector
from app.services.sources.lever import LeverConnector

logger = logging.getLogger("jobhunter.aggregator")

CONNECTORS = {
    SourceType.adzuna: AdzunaConnector(),
    SourceType.jooble: JoobleConnector(),
    SourceType.greenhouse: GreenhouseConnector(),
    SourceType.lever: LeverConnector(),
}


def _gb_is_target(settings_row: Optional[SearchSettings]) -> bool:
    """
    The UK sponsor-register check only makes sense for GB. Default is True
    (GB) when settings haven't been configured yet, matching SearchSettings'
    own default of target_countries="GB".
    """
    if not settings_row or not settings_row.target_countries:
        return True
    countries = [c.strip().lower() for c in settings_row.target_countries.split(",") if c.strip()]
    return "gb" in countries


def store_raw_jobs(
    session: Session, raw_jobs: List[RawJob], settings_row: Optional[SearchSettings] = None
) -> Tuple[List[JobListing], int]:
    """
    De-duplicates `raw_jobs` against the DB (by source + source_job_id),
    stores the genuinely new ones -- with work-mode classification, a
    sponsorship-language heuristic, and (when GB is a target country) a UK
    sponsor-register lookup all applied -- and returns
    (newly_created_listings, duplicate_count).
    """
    if settings_row is None:
        settings_row = session.exec(select(SearchSettings)).first()
    check_uk_register = _gb_is_target(settings_row)

    created: List[JobListing] = []
    duplicate_count = 0

    for raw in raw_jobs:
        exists = session.exec(
            select(JobListing).where(
                JobListing.source == raw.source,
                JobListing.source_job_id == raw.source_job_id,
            )
        ).first()
        if exists:
            duplicate_count += 1
            continue

        sponsorship_status, sponsorship_reasoning = sponsorship.classify(raw.description)
        mode = work_mode.classify(raw.title, raw.location, raw.description, remote_flag=raw.remote)

        if check_uk_register and (not raw.country or raw.country.upper() == "GB"):
            uk_licensed, uk_reasoning = uk_sponsor_register.is_licensed(raw.company)
        else:
            uk_licensed, uk_reasoning = None, "Not checked -- GB isn't one of your target countries."

        listing = JobListing(
            source=raw.source,
            source_job_id=raw.source_job_id,
            title=raw.title,
            company=raw.company,
            location=raw.location,
            country=raw.country,
            remote=raw.remote,
            work_mode=mode,
            description=raw.description,
            url=raw.url,
            salary_text=raw.salary_text,
            posted_date=raw.posted_date,
            status=JobStatus.new,
            sponsorship_status=sponsorship_status,
            sponsorship_reasoning=sponsorship_reasoning,
            uk_sponsor_licensed=uk_licensed,
            uk_sponsor_reasoning=uk_reasoning,
        )
        session.add(listing)
        created.append(listing)

    session.commit()
    for listing in created:
        session.refresh(listing)

    return created, duplicate_count


async def run_fetch(session: Session) -> FetchResult:
    profile = session.exec(select(Profile)).first()
    if profile is None:
        profile = Profile()  # empty profile -> connectors that need it just return []

    settings_row = session.exec(select(SearchSettings)).first()
    countries = []
    if settings_row and settings_row.target_countries:
        countries = [c.strip() for c in settings_row.target_countries.split(",") if c.strip()]
    if not countries:
        countries = ["gb"]  # SearchSettings defaults to GB; keep the same default when no row exists yet

    tracked = session.exec(select(TrackedCompany).where(TrackedCompany.active == True)).all()  # noqa: E712
    greenhouse_slugs = [t.slug for t in tracked if t.source_type == SourceType.greenhouse]
    lever_slugs = [t.slug for t in tracked if t.source_type == SourceType.lever]

    all_raw: List[RawJob] = []
    errors: List[str] = []
    sources_queried: List[str] = []

    for source_type, connector in CONNECTORS.items():
        try:
            if source_type == SourceType.greenhouse:
                jobs = await connector.fetch(profile, companies=greenhouse_slugs)
            elif source_type == SourceType.lever:
                jobs = await connector.fetch(profile, companies=lever_slugs)
            elif source_type == SourceType.adzuna:
                jobs = await connector.fetch(profile, countries=countries)
            else:
                jobs = await connector.fetch(profile)
            sources_queried.append(source_type.value)
            all_raw.extend(jobs)
        except Exception as exc:  # noqa: BLE001 -- one bad source must not kill the run
            logger.exception("Source %s failed", source_type)
            errors.append(f"{source_type.value}: {exc}")

    created, duplicate_count = store_raw_jobs(session, all_raw, settings_row=settings_row)

    return FetchResult(
        fetched=len(all_raw),
        new=len(created),
        duplicates=duplicate_count,
        sources_queried=sources_queried,
        errors=errors,
    )
