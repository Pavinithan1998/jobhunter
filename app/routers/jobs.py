from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.auth import require_api_key
from app.database import get_session
from app.models import JobListing, JobStatus, SearchSettings, SponsorshipStatus, WorkMode
from app.schemas import (
    DailyDigest,
    FetchResult,
    JobListingOut,
    JobStatusUpdate,
    ScoreResult,
    WebSearchRequest,
    WebSearchResult,
)
from app.services.aggregator import run_fetch, store_raw_jobs
from app.services.llm_client import LLMNotConfigured
from app.services.matching import score_job
from app.services.matching import score_pending_jobs
from app.services.sources.web_search import WebJobSearchConnector
from app.utils.time import utcnow

router = APIRouter(prefix="/api/jobs", tags=["Jobs"], dependencies=[Depends(require_api_key)])

_web_search_connector = WebJobSearchConnector()


@router.post("/fetch", response_model=FetchResult)
async def fetch_jobs(session: Session = Depends(get_session)):
    """
    Trigger an immediate fetch across every configured standing source
    (Adzuna, Jooble, and any tracked Greenhouse/Lever companies), scoped to
    the countries in your Settings if you've set any. This is the same
    thing the daily scheduler runs automatically -- call it any time you
    don't want to wait.
    """
    return await run_fetch(session)


@router.post("/search-web", response_model=WebSearchResult)
async def search_web(payload: WebSearchRequest, session: Session = Depends(get_session)):
    """
    On-demand internet-wide job search (not just the standing sources): runs
    a live query through SerpApi's Google Jobs engine, which itself
    aggregates postings from LinkedIn, Indeed, Glassdoor, company career
    sites, and more -- so this is the closest thing to "search the whole
    internet right now" the app offers, without scraping anything directly
    (see app/services/sources/web_search.py for why). Requires SERPAPI_KEY.

    New jobs found are stored (de-duplicated like everything else) and, if
    ANTHROPIC_API_KEY is configured, scored immediately so you see results
    with a relevance score and sponsorship read straight away rather than
    waiting for the next batch score.
    """
    try:
        raw_jobs = await _web_search_connector.search(
            query=payload.query,
            location=payload.location,
            country=payload.country,
            remote_only=payload.remote_only,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    settings_row = session.exec(select(SearchSettings)).first()
    created, duplicate_count = store_raw_jobs(session, raw_jobs, settings_row=settings_row)

    scored_count = 0
    errors: list[str] = []
    profile = None
    if created:
        from app.models import Profile

        profile = session.exec(select(Profile)).first()

    if profile and profile.cv_raw_text:
        for job in created:
            try:
                score, reasoning, sponsorship_status, sponsorship_reasoning = score_job(job, profile)
            except LLMNotConfigured as exc:
                errors.append(str(exc))
                break
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Job {job.id}: {exc}")
                continue
            job.relevance_score = score
            job.relevance_reasoning = reasoning
            job.sponsorship_status = sponsorship_status
            if sponsorship_reasoning:
                job.sponsorship_reasoning = sponsorship_reasoning
            job.status = JobStatus.scored
            session.add(job)
            scored_count += 1
        session.commit()
        for job in created:
            session.refresh(job)

    return WebSearchResult(
        fetched=len(raw_jobs),
        new=len(created),
        duplicates=duplicate_count,
        scored=scored_count,
        jobs=[JobListingOut.model_validate(job) for job in created],
        errors=errors,
    )


@router.post("/score-batch", response_model=ScoreResult)
def score_jobs(limit: int = Query(100, le=500), session: Session = Depends(get_session)):
    """Run relevance scoring on every job currently in 'new' status."""
    return score_pending_jobs(session, limit=limit)


@router.get("", response_model=list[JobListingOut])
def list_jobs(
    status: Optional[JobStatus] = None,
    min_score: Optional[float] = None,
    search: Optional[str] = Query(None, description="Matches against title, company, or description"),
    work_mode: Optional[WorkMode] = Query(None, description="Filter by remote/hybrid/onsite classification"),
    country: Optional[str] = Query(None, description="ISO country code, e.g. 'GB'"),
    sponsorship: Optional[SponsorshipStatus] = Query(None, description="Filter by visa sponsorship assessment"),
    uk_sponsor_licensed: Optional[bool] = Query(
        None, description="Filter by UK Home Office sponsor register match (true/false)"
    ),
    limit: int = Query(50, le=500),
    offset: int = 0,
    session: Session = Depends(get_session),
):
    query = select(JobListing)
    if status:
        query = query.where(JobListing.status == status)
    if min_score is not None:
        query = query.where(JobListing.relevance_score >= min_score)
    if work_mode:
        query = query.where(JobListing.work_mode == work_mode)
    if country:
        query = query.where(JobListing.country == country.upper())
    if sponsorship:
        query = query.where(JobListing.sponsorship_status == sponsorship)
    if uk_sponsor_licensed is not None:
        query = query.where(JobListing.uk_sponsor_licensed == uk_sponsor_licensed)
    query = query.order_by(JobListing.relevance_score.desc().nullslast(), JobListing.fetched_at.desc())
    query = query.offset(offset).limit(limit)

    jobs = session.exec(query).all()

    if search:
        needle = search.lower()
        jobs = [
            j for j in jobs
            if needle in j.title.lower() or needle in j.company.lower() or needle in j.description.lower()
        ]

    return jobs


@router.get("/digest/today", response_model=DailyDigest)
def daily_digest(min_score: Optional[float] = None, session: Session = Depends(get_session)):
    """
    The 'end of day, show me what's new and relevant' view: jobs fetched
    today, above a relevance threshold, best first. If `min_score` isn't
    passed, uses your Settings' `digest_min_score` (default 60). Also
    applies your Settings' work-mode and sponsorship-required filters if
    you've turned them on.
    """
    settings_row = session.exec(select(SearchSettings)).first()
    threshold = min_score if min_score is not None else (settings_row.digest_min_score if settings_row else 60.0)

    since = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    query = (
        select(JobListing)
        .where(JobListing.fetched_at >= since)
        .where(JobListing.relevance_score >= threshold)
    )
    if settings_row and settings_row.work_mode != WorkMode.any:
        query = query.where(
            (JobListing.work_mode == settings_row.work_mode) | (JobListing.work_mode == WorkMode.unclear)
        )
    if settings_row and settings_row.require_sponsorship:
        query = query.where(JobListing.sponsorship_status != SponsorshipStatus.unlikely)
    query = query.order_by(JobListing.relevance_score.desc())

    jobs = session.exec(query).all()
    return DailyDigest(date=since.date().isoformat(), count=len(jobs), jobs=jobs)


@router.get("/{job_id}", response_model=JobListingOut)
def get_job(job_id: int, session: Session = Depends(get_session)):
    job = session.get(JobListing, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.patch("/{job_id}/status", response_model=JobListingOut)
def update_status(job_id: int, payload: JobStatusUpdate, session: Session = Depends(get_session)):
    job = session.get(JobListing, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    job.status = payload.status
    job.updated_at = utcnow()
    session.add(job)

    if payload.notes:
        from app.models import ApplicationEvent

        session.add(ApplicationEvent(job_id=job.id, event_type="note", notes=payload.notes))

    session.commit()
    session.refresh(job)
    return job


@router.delete("/{job_id}")
def delete_job(job_id: int, session: Session = Depends(get_session)):
    job = session.get(JobListing, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    session.delete(job)
    session.commit()
    return {"deleted": job_id}
