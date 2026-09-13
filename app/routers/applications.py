from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.auth import require_api_key
from app.database import get_session
from app.models import ApplicationChannel, ApplicationEvent, ApplicationStage, JobListing, JobStatus
from app.schemas import ApplicationEventIn, ApplicationEventOut, ApplicationStageUpdate, JobListingOut
from app.utils.time import utcnow

router = APIRouter(tags=["Applications"], dependencies=[Depends(require_api_key)])

_EVENT_TO_STATUS = {
    "applied": JobStatus.applied,
    "interview": JobStatus.interviewing,
    "offer": JobStatus.offer,
    "rejected": JobStatus.rejected,
}

_EVENT_TO_STAGE = {
    "applied": ApplicationStage.no_response,
    "interview": ApplicationStage.interviewing,
    "offer": ApplicationStage.offer,
    "rejected": ApplicationStage.rejected,
}

# The Applications page's stage transitions also sync the coarser JobStatus
# field, so existing status-based views (dashboard counts, /api/jobs
# filters) stay consistent with whatever's set here.
_STAGE_TO_STATUS = {
    ApplicationStage.no_response: JobStatus.applied,
    ApplicationStage.responded: JobStatus.applied,
    ApplicationStage.interviewing: JobStatus.interviewing,
    ApplicationStage.offer: JobStatus.offer,
    ApplicationStage.rejected: JobStatus.rejected,
}


@router.post("/api/jobs/{job_id}/apply", response_model=JobListingOut)
def mark_applied(job_id: int, notes: str = "", session: Session = Depends(get_session)):
    """
    Record that you've submitted this application. This is a deliberate,
    explicit action -- the app never submits an application on its own; it
    prepares the tailored documents, you apply on the actual site, then you
    confirm it here so the tracker stays accurate.

    Sets `application_stage` to `no_response` (the Applications page's
    default starting point) -- move it forward from there with
    PATCH /api/jobs/{job_id}/application-stage as you hear back.
    """
    job = session.get(JobListing, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    job.status = JobStatus.applied
    job.application_stage = ApplicationStage.no_response
    job.updated_at = utcnow()
    session.add(job)
    session.add(ApplicationEvent(job_id=job_id, event_type="applied", notes=notes))
    session.commit()
    session.refresh(job)
    return job


@router.patch("/api/jobs/{job_id}/application-stage", response_model=JobListingOut)
def update_application_stage(job_id: int, payload: ApplicationStageUpdate, session: Session = Depends(get_session)):
    """
    Move a job through the Applications page's tracking stages:
    no_response -> responded -> interviewing -> offer / rejected. This is
    the dedicated setter for that page; it also keeps the job's coarser
    `status` field in sync (e.g. setting stage to 'interviewing' also sets
    status to 'interviewing').
    """
    job = session.get(JobListing, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.application_stage is None:
        raise HTTPException(
            400, "This job hasn't been marked applied yet -- call POST /api/jobs/{job_id}/apply first."
        )

    job.application_stage = payload.stage
    job.status = _STAGE_TO_STATUS[payload.stage]
    job.updated_at = utcnow()
    session.add(job)
    session.add(ApplicationEvent(job_id=job_id, event_type="stage_change", notes=payload.notes or payload.stage.value))
    session.commit()
    session.refresh(job)
    return job


@router.post("/api/jobs/{job_id}/events", response_model=ApplicationEventOut)
def add_event(job_id: int, payload: ApplicationEventIn, session: Session = Depends(get_session)):
    """Log an interview, offer, rejection, or free-text note against a job."""
    job = session.get(JobListing, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    event = ApplicationEvent(job_id=job_id, event_type=payload.event_type, notes=payload.notes)
    session.add(event)

    new_status = _EVENT_TO_STATUS.get(payload.event_type)
    if new_status:
        job.status = new_status
        job.application_stage = _EVENT_TO_STAGE.get(payload.event_type, job.application_stage)
        job.updated_at = utcnow()
        session.add(job)

    session.commit()
    session.refresh(event)
    return event


@router.get("/api/jobs/{job_id}/events", response_model=list[ApplicationEventOut])
def list_events(job_id: int, session: Session = Depends(get_session)):
    return session.exec(
        select(ApplicationEvent).where(ApplicationEvent.job_id == job_id).order_by(ApplicationEvent.created_at)
    ).all()


@router.get("/api/applications", response_model=list[JobListingOut])
def list_applications(
    status: Optional[JobStatus] = Query(None, description="Filter to one coarse status; omit for all applied+ jobs"),
    stage: Optional[ApplicationStage] = Query(None, description="Filter by Applications-page stage"),
    channel: Optional[ApplicationChannel] = Query(
        None, description="Filter to 'manual_search' or 'automated_search' applications"
    ),
    session: Session = Depends(get_session),
):
    """
    The Applications page: every job you've applied to, across both
    channels -- jobs you found and pasted in yourself (`manual_search`) and
    jobs the app fetched for you (`automated_search`) -- with its current
    tracking stage. Defaults to every job that's reached at least the
    'applied' status; narrow with `status`, `stage`, or `channel`.
    """
    tracked_statuses = [JobStatus.applied, JobStatus.interviewing, JobStatus.offer, JobStatus.rejected]
    query = select(JobListing)
    if status:
        query = query.where(JobListing.status == status)
    else:
        query = query.where(JobListing.status.in_(tracked_statuses))
    if stage:
        query = query.where(JobListing.application_stage == stage)
    query = query.order_by(JobListing.updated_at.desc())

    jobs = session.exec(query).all()

    if channel:
        jobs = [j for j in jobs if j.application_channel == channel]

    return jobs
