"""
Request/response schemas that are NOT 1:1 with a DB table (create/update
payloads, composite responses, dashboard summaries).
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    ApplicationChannel,
    ApplicationStage,
    DocType,
    JobStatus,
    SourceType,
    SponsorshipStatus,
    WorkMode,
)


# --- Profile ----------------------------------------------------------------
class ProfileIn(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    target_titles: str = Field("", description="Comma-separated job titles, e.g. 'ML Engineer, MLOps Engineer'")
    target_locations: str = Field("", description="Comma-separated, e.g. 'London, Remote UK'")
    remote_preference: str = Field("any", pattern="^(remote|hybrid|onsite|any)$")
    seniority: str = ""
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    currency: str = "GBP"
    must_have_keywords: str = ""
    exclude_keywords: str = ""


class ProfileOut(ProfileIn):
    id: int
    cv_filename: str = ""
    has_cv: bool = False
    updated_at: datetime


# --- Search settings: the Settings page (country, work mode, sponsorship) --
class SearchSettingsIn(BaseModel):
    target_countries: str = Field(
        "GB",
        description=(
            "Comma-separated ISO country codes to search/apply in, e.g. 'gb' or 'gb,ca,us'. "
            "Defaults to the UK -- change to 'ca', 'us', etc. to search elsewhere instead."
        ),
    )
    work_mode: WorkMode = Field(
        WorkMode.any,
        description="Hard filter: 'remote', 'hybrid', 'onsite', or 'any' (no filter). Jobs with an unclear work mode are never auto-dismissed by this.",
    )
    require_sponsorship: bool = Field(
        False, description="Hard filter: auto-dismiss jobs assessed as unlikely to sponsor a visa"
    )
    excluded_companies: str = Field("", description="Comma-separated company names to never show")
    digest_min_score: float = Field(60.0, ge=0, le=100, description="Default relevance threshold for the daily digest")


class SearchSettingsOut(SearchSettingsIn):
    id: int
    updated_at: datetime


# --- Tracked companies (Greenhouse / Lever) ---------------------------------
class TrackedCompanyIn(BaseModel):
    slug: str
    display_name: str = ""


class TrackedCompanyOut(BaseModel):
    id: int
    source_type: SourceType
    slug: str
    display_name: str
    active: bool
    created_at: datetime


# --- Manual job entry (LinkedIn / Indeed paste-in) --------------------------
class ManualJobIn(BaseModel):
    title: str
    company: str
    location: str = ""
    country: str = Field("", description="ISO country code, e.g. 'GB' -- optional, for filtering")
    description: str
    url: str = ""
    salary_text: str = ""
    remote: bool = False


# --- On-demand internet job search (SerpApi Google Jobs) --------------------
class WebSearchRequest(BaseModel):
    query: str = Field(..., description="e.g. 'Machine Learning Engineer'")
    location: str = Field("", description="Free-text location, e.g. 'London, UK'")
    country: str = Field("", description="ISO country code, e.g. 'gb', 'us' -- maps to SerpApi's 'gl' param")
    remote_only: bool = False


# --- UK sponsor register -----------------------------------------------
class UKSponsorRegisterStatus(BaseModel):
    downloaded: bool
    record_count: int
    refreshed_at: Optional[str] = None
    source_url: Optional[str] = None


# --- Job listing --------------------------------------------------------
class JobListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: SourceType
    title: str
    company: str
    location: str
    country: str
    remote: bool
    work_mode: WorkMode
    description: str
    url: str
    salary_text: str
    posted_date: Optional[datetime]
    status: JobStatus
    relevance_score: Optional[float]
    relevance_reasoning: str
    sponsorship_status: Optional[SponsorshipStatus]
    sponsorship_reasoning: str
    uk_sponsor_licensed: Optional[bool]
    uk_sponsor_reasoning: str
    application_stage: Optional[ApplicationStage]
    application_channel: ApplicationChannel
    fetched_at: datetime


class JobStatusUpdate(BaseModel):
    status: JobStatus
    notes: str = ""


class FetchResult(BaseModel):
    fetched: int
    new: int
    duplicates: int
    sources_queried: List[str]
    errors: List[str] = []


class WebSearchResult(BaseModel):
    fetched: int
    new: int
    duplicates: int
    scored: int
    jobs: List[JobListingOut]
    errors: List[str] = []


class ScoreResult(BaseModel):
    scored: int
    errors: List[str] = []


# --- Documents ---------------------------------------------------------
class TailorRequest(BaseModel):
    generate_cover_letter: bool = True


class GeneratedDocumentOut(BaseModel):
    id: int
    job_id: int
    doc_type: DocType
    content_text: str
    download_url: str
    created_at: datetime


# --- Applications --------------------------------------------------
class ApplicationEventIn(BaseModel):
    event_type: str = Field(..., pattern="^(applied|interview|offer|rejected|note)$")
    notes: str = ""


class ApplicationEventOut(BaseModel):
    id: int
    job_id: int
    event_type: str
    notes: str
    created_at: datetime


class ApplicationStageUpdate(BaseModel):
    stage: ApplicationStage
    notes: str = ""


# --- Dashboard -----------------------------------------------------
class DashboardSummary(BaseModel):
    total_jobs: int
    by_status: dict
    new_today: int
    shortlisted_unapplied: int
    applied_last_7_days: int


class DailyDigest(BaseModel):
    date: str
    count: int
    jobs: List[JobListingOut]
