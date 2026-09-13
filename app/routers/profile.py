import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from app.auth import require_api_key
from app.config import get_settings
from app.database import get_session
from app.models import Profile
from app.schemas import ProfileIn, ProfileOut
from app.utils.cv_parser import extract_text
from app.utils.time import utcnow

router = APIRouter(prefix="/api/profile", tags=["Profile"], dependencies=[Depends(require_api_key)])


def _to_out(profile: Profile) -> ProfileOut:
    return ProfileOut(
        id=profile.id,
        full_name=profile.full_name,
        email=profile.email,
        phone=profile.phone,
        location=profile.location,
        target_titles=profile.target_titles,
        target_locations=profile.target_locations,
        remote_preference=profile.remote_preference,
        seniority=profile.seniority,
        min_salary=profile.min_salary,
        max_salary=profile.max_salary,
        currency=profile.currency,
        must_have_keywords=profile.must_have_keywords,
        exclude_keywords=profile.exclude_keywords,
        cv_filename=profile.cv_filename,
        has_cv=bool(profile.cv_raw_text),
        updated_at=profile.updated_at,
    )


@router.get("", response_model=ProfileOut)
def get_profile(session: Session = Depends(get_session)):
    profile = session.exec(select(Profile)).first()
    if not profile:
        raise HTTPException(404, "No profile set up yet. POST here first.")
    return _to_out(profile)


@router.post("", response_model=ProfileOut)
def upsert_profile(payload: ProfileIn, session: Session = Depends(get_session)):
    """Create the profile if it doesn't exist yet, otherwise update it. Single-user app -- one row."""
    profile = session.exec(select(Profile)).first()
    if not profile:
        profile = Profile()

    for field, value in payload.model_dump().items():
        setattr(profile, field, value)
    profile.updated_at = utcnow()

    session.add(profile)
    session.commit()
    session.refresh(profile)
    return _to_out(profile)


@router.post("/cv", response_model=ProfileOut)
def upload_cv(file: UploadFile = File(...), session: Session = Depends(get_session)):
    """Upload the master CV (.pdf, .docx or .txt). It is parsed to plain text and stored."""
    settings = get_settings()
    profile = session.exec(select(Profile)).first()
    if not profile:
        profile = Profile()

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".docx", ".txt"):
        raise HTTPException(400, "Only .pdf, .docx or .txt CVs are supported.")

    from app.config import UPLOADS_DIR

    dest = UPLOADS_DIR / f"master_cv{suffix}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        text = extract_text(dest)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    profile.cv_raw_text = text
    profile.cv_filename = file.filename
    profile.updated_at = utcnow()

    session.add(profile)
    session.commit()
    session.refresh(profile)
    return _to_out(profile)


@router.get("/cv/text")
def get_cv_text(session: Session = Depends(get_session)):
    profile = session.exec(select(Profile)).first()
    if not profile or not profile.cv_raw_text:
        raise HTTPException(404, "No CV uploaded yet.")
    return {"filename": profile.cv_filename, "text": profile.cv_raw_text}
