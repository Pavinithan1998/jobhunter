"""
SQLModel table definitions. Each class is both the DB table schema and a
Pydantic model, so it can be returned directly from API endpoints.
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel

from app.utils.time import utcnow


class JobStatus(str, Enum):
    new = "new"                # just fetched, not yet scored
    scored = "scored"          # relevance score assigned
    shortlisted = "shortlisted"  # user wants to apply
    dismissed = "dismissed"    # user isn't interested
    applied = "applied"
    interviewing = "interviewing"
    offer = "offer"
    rejected = "rejected"


class SourceType(str, Enum):
    adzuna = "adzuna"
    jooble = "jooble"
    greenhouse = "greenhouse"
    lever = "lever"
    manual = "manual"          # pasted in by hand (e.g. from LinkedIn/Indeed)
    web_search = "web_search"  # on-demand internet job search (SerpApi Google Jobs)


class DocType(str, Enum):
    cv = "cv"
    cover_letter = "cover_letter"


class SponsorshipStatus(str, Enum):
    likely = "likely"       # description mentions/implies visa sponsorship is available
    unlikely = "unlikely"   # description says no sponsorship / must already have right to work
    unclear = "unclear"     # not mentioned either way


class WorkMode(str, Enum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"
    any = "any"          # settings only: no work-mode filter applied
    unclear = "unclear"  # job listings only: couldn't tell from title/location/description


class ApplicationChannel(str, Enum):
    manual_search = "manual_search"        # you found it yourself (source == manual)
    automated_search = "automated_search"  # the app fetched it (Adzuna/Jooble/Greenhouse/Lever/web search)


class ApplicationStage(str, Enum):
    """
    The post-application tracking stages shown on the Applications page.
    Set automatically to `no_response` the moment a job is marked applied
    (POST /api/jobs/{id}/apply), and moved forward from there via
    PATCH /api/jobs/{id}/application-stage.
    """
    no_response = "no_response"
    responded = "responded"
    interviewing = "interviewing"
    offer = "offer"          # "selected"
    rejected = "rejected"


# ---------------------------------------------------------------------------
# Profile: one row, one user. Holds everything needed to filter jobs and
# tailor documents.
# ---------------------------------------------------------------------------
class Profile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""

    target_titles: str = ""        # comma-separated, e.g. "ML Engineer, MLOps Engineer"
    target_locations: str = ""     # comma-separated, e.g. "London, Remote UK"
    remote_preference: str = "any"  # "remote" | "hybrid" | "onsite" | "any" -- nudges the LLM scoring prompt
    seniority: str = ""            # e.g. "junior", "mid", "senior"
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    currency: str = "GBP"

    must_have_keywords: str = ""   # comma-separated
    exclude_keywords: str = ""     # comma-separated

    cv_raw_text: str = ""          # parsed plain text of the uploaded master CV
    cv_filename: str = ""

    updated_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# Tracked companies for the ATS-board connectors (Greenhouse / Lever). The
# user adds company slugs they want polled every day.
# ---------------------------------------------------------------------------
class TrackedCompany(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_type: SourceType
    slug: str                      # the company's board slug, e.g. "stripe"
    display_name: str = ""
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# Settings: the "Settings page" -- search-wide preferences, separate from
# Profile (which is CV + identity). One row, same single-user pattern.
# ---------------------------------------------------------------------------
class SearchSettings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    # Comma-separated ISO country codes, e.g. "gb" or "gb,ca,us". Defaults to
    # the UK -- this app is built UK-sponsorship-first, with other countries
    # as an explicit opt-in switch, not the other way round.
    target_countries: str = "GB"

    # Hard filter: "remote", "hybrid", "onsite", or "any". Unlike a simple
    # remote/not-remote toggle, this lets "hybrid only" or "onsite only" be
    # expressed directly, matching JobListing.work_mode.
    work_mode: WorkMode = WorkMode.any
    require_sponsorship: bool = False   # hard filter: auto-dismiss jobs assessed as won't-sponsor
    excluded_companies: str = ""        # comma-separated company names to never show
    digest_min_score: float = 60.0      # default relevance threshold for the daily digest

    updated_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# JobListing: every job the system has seen, from any source.
# ---------------------------------------------------------------------------
class JobListing(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    source: SourceType
    source_job_id: str = Field(index=True)   # external id, used for de-duplication
    title: str
    company: str
    location: str = ""
    country: str = ""              # ISO country code when the source tells us, else ""
    remote: bool = False           # raw "is this remote" flag as reported by the source
    work_mode: WorkMode = WorkMode.unclear  # heuristic remote/hybrid/onsite classification
    description: str = ""
    url: str = ""
    salary_text: str = ""
    posted_date: Optional[datetime] = None

    status: JobStatus = JobStatus.new
    relevance_score: Optional[float] = None   # 0-100
    relevance_reasoning: str = ""

    sponsorship_status: Optional[SponsorshipStatus] = None
    sponsorship_reasoning: str = ""

    # UK Home Office public register of licensed Worker/Temporary Worker
    # sponsors: True/False when the company was matched against the current
    # register, None when not checked (e.g. GB isn't a target country, or
    # the register hasn't been downloaded yet).
    uk_sponsor_licensed: Optional[bool] = None
    uk_sponsor_reasoning: str = ""

    # Set once the job is marked applied; tracks post-application progress
    # independently of the coarser `status` field. See ApplicationStage.
    application_stage: Optional[ApplicationStage] = None

    fetched_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def application_channel(self) -> ApplicationChannel:
        """Not a stored column -- derived from `source` for the Applications page's filter/grouping."""
        return ApplicationChannel.manual_search if self.source == SourceType.manual else ApplicationChannel.automated_search


# ---------------------------------------------------------------------------
# Generated documents (tailored CV / cover letter) per job.
# ---------------------------------------------------------------------------
class GeneratedDocument(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="joblisting.id")
    doc_type: DocType
    content_text: str = ""
    file_path: str = ""            # path under storage/documents
    created_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# Application timeline: every status change / note for a job, kept as a log
# so the dashboard can show a history, not just the current status.
# ---------------------------------------------------------------------------
class ApplicationEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="joblisting.id")
    event_type: str                # "applied" | "interview" | "offer" | "rejected" | "note" | "stage_change"
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)
