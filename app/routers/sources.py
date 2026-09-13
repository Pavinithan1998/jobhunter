import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth import require_api_key
from app.database import get_session
from app.models import SourceType, TrackedCompany
from app.schemas import (
    JobListingOut,
    ManualJobIn,
    TrackedCompanyIn,
    TrackedCompanyOut,
    UKSponsorRegisterStatus,
)
from app.services import uk_sponsor_register
from app.services.aggregator import store_raw_jobs
from app.services.sources.base import RawJob

router = APIRouter(prefix="/api/sources", tags=["Job Sources"], dependencies=[Depends(require_api_key)])


@router.get("/status")
def sources_status():
    """
    Which connectors are configured and ready. Useful for the frontend to
    show setup progress / warnings (e.g. "Adzuna: not configured").
    """
    from app.config import get_settings

    settings = get_settings()
    return {
        "adzuna": bool(settings.adzuna_app_id and settings.adzuna_app_key),
        "jooble": bool(settings.jooble_api_key),
        "greenhouse": "configure via tracked companies (no key needed)",
        "lever": "configure via tracked companies (no key needed)",
        "web_search": bool(settings.serpapi_key),
        "uk_sponsor_register": uk_sponsor_register.get_status()["downloaded"],
        "linkedin": "not supported for auto-fetch/auto-apply -- use /api/sources/manual-job to add a listing by hand",
        "indeed": "not supported for auto-fetch/auto-apply -- use /api/sources/manual-job to add a listing by hand",
    }


def _company_router(source_type: SourceType, path: str):
    sub = APIRouter()

    @sub.get(f"/{path}", response_model=list[TrackedCompanyOut])
    def list_companies(session: Session = Depends(get_session)):
        return session.exec(select(TrackedCompany).where(TrackedCompany.source_type == source_type)).all()

    @sub.post(f"/{path}", response_model=TrackedCompanyOut)
    def add_company(payload: TrackedCompanyIn, session: Session = Depends(get_session)):
        existing = session.exec(
            select(TrackedCompany).where(
                TrackedCompany.source_type == source_type, TrackedCompany.slug == payload.slug
            )
        ).first()
        if existing:
            raise HTTPException(400, f"'{payload.slug}' is already tracked for {source_type.value}.")
        company = TrackedCompany(
            source_type=source_type, slug=payload.slug, display_name=payload.display_name or payload.slug
        )
        session.add(company)
        session.commit()
        session.refresh(company)
        return company

    @sub.delete(f"/{path}/{{company_id}}")
    def remove_company(company_id: int, session: Session = Depends(get_session)):
        company = session.get(TrackedCompany, company_id)
        if not company:
            raise HTTPException(404, "Not found")
        session.delete(company)
        session.commit()
        return {"deleted": company_id}

    return sub


router.include_router(_company_router(SourceType.greenhouse, "greenhouse"))
router.include_router(_company_router(SourceType.lever, "lever"))


@router.post("/manual-job", response_model=JobListingOut)
def add_manual_job(payload: ManualJobIn, session: Session = Depends(get_session)):
    """
    Add a job you found yourself -- e.g. on LinkedIn or Indeed -- by pasting
    its details in. It goes through the same work-mode classification,
    sponsorship-language heuristic, UK sponsor-register lookup, and later
    scoring/tailoring pipeline as auto-fetched jobs. This is the supported
    way to bring LinkedIn/Indeed listings into the app (see
    /api/sources/status for why there's no automatic connector for those two).
    """
    raw = RawJob(
        source=SourceType.manual,
        source_job_id=str(uuid.uuid4()),  # always unique -- manual entries are never "duplicates"
        title=payload.title,
        company=payload.company,
        location=payload.location,
        country=payload.country.upper() if payload.country else "",
        remote=payload.remote,
        description=payload.description,
        url=payload.url,
        salary_text=payload.salary_text,
    )
    created, _ = store_raw_jobs(session, [raw])
    return created[0]


@router.post("/uk-sponsor-register/refresh", response_model=UKSponsorRegisterStatus)
async def refresh_uk_sponsor_register():
    """
    Downloads the current UK Home Office register of licensed Worker/
    Temporary Worker sponsors and caches it locally. Run this every so
    often (weekly is plenty -- the register itself doesn't change daily) so
    that `uk_sponsor_licensed` on job listings reflects current data.
    """
    try:
        meta = await uk_sponsor_register.refresh()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Couldn't refresh the UK sponsor register: {exc}")
    return UKSponsorRegisterStatus(downloaded=True, **meta)


@router.get("/uk-sponsor-register/status", response_model=UKSponsorRegisterStatus)
def uk_sponsor_register_status():
    """Whether the register has been downloaded yet, and when it was last refreshed."""
    return UKSponsorRegisterStatus(**uk_sponsor_register.get_status())
