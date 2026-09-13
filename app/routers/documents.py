from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.auth import require_api_key
from app.config import BASE_DIR
from app.database import get_session
from app.models import GeneratedDocument, JobListing, Profile
from app.schemas import GeneratedDocumentOut, TailorRequest
from app.services import documents as doc_service
from app.services.llm_client import LLMNotConfigured

router = APIRouter(tags=["Documents"], dependencies=[Depends(require_api_key)])


def _to_out(doc: GeneratedDocument) -> GeneratedDocumentOut:
    return GeneratedDocumentOut(
        id=doc.id,
        job_id=doc.job_id,
        doc_type=doc.doc_type,
        content_text=doc.content_text,
        download_url=f"/api/documents/{doc.id}/download",
        created_at=doc.created_at,
    )


@router.post("/api/jobs/{job_id}/tailor", response_model=list[GeneratedDocumentOut])
def tailor_for_job(job_id: int, payload: TailorRequest, session: Session = Depends(get_session)):
    """
    Generate a lightly-tailored CV (and optionally a cover letter) for this
    job, from the profile's master CV. Produces downloadable .docx files.
    """
    job = session.get(JobListing, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    profile = session.exec(select(Profile)).first()
    if not profile or not profile.cv_raw_text:
        raise HTTPException(400, "Upload a master CV first via POST /api/profile/cv")

    try:
        docs = doc_service.create_tailored_documents(
            session, job, profile, generate_cover_letter=payload.generate_cover_letter
        )
    except LLMNotConfigured as exc:
        raise HTTPException(400, str(exc))
    return [_to_out(d) for d in docs]


@router.get("/api/jobs/{job_id}/documents", response_model=list[GeneratedDocumentOut])
def list_documents_for_job(job_id: int, session: Session = Depends(get_session)):
    docs = session.exec(select(GeneratedDocument).where(GeneratedDocument.job_id == job_id)).all()
    return [_to_out(d) for d in docs]


@router.get("/api/documents/{document_id}/download")
def download_document(document_id: int, session: Session = Depends(get_session)):
    doc = session.get(GeneratedDocument, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")

    file_path = BASE_DIR / doc.file_path
    if not file_path.exists():
        raise HTTPException(410, "File is no longer on disk")

    return FileResponse(
        path=str(file_path),
        filename=Path(doc.file_path).name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
