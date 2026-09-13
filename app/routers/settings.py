from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth import require_api_key
from app.database import get_session
from app.models import SearchSettings
from app.schemas import SearchSettingsIn, SearchSettingsOut

router = APIRouter(prefix="/api/settings", tags=["Settings"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=SearchSettingsOut)
def get_settings_row(session: Session = Depends(get_session)):
    """
    Search-wide preferences: which country/countries to search/apply in
    (defaults to the UK), remote/hybrid/onsite work mode, visa sponsorship
    requirement, excluded companies, and the default digest threshold.
    Separate from /api/profile (identity + CV) -- this is the "settings
    page" a frontend should build a dedicated screen for.
    """
    settings_row = session.exec(select(SearchSettings)).first()
    if not settings_row:
        raise HTTPException(404, "Settings haven't been set up yet. POST here first (defaults are sensible).")
    return settings_row


@router.post("", response_model=SearchSettingsOut)
def upsert_settings(payload: SearchSettingsIn, session: Session = Depends(get_session)):
    """Create settings on first call, update them on every call after (upsert -- one row)."""
    from app.utils.time import utcnow

    settings_row = session.exec(select(SearchSettings)).first()
    if not settings_row:
        settings_row = SearchSettings()

    for field, value in payload.model_dump().items():
        setattr(settings_row, field, value)
    settings_row.updated_at = utcnow()

    session.add(settings_row)
    session.commit()
    session.refresh(settings_row)
    return settings_row
