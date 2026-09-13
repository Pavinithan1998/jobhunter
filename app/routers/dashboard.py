from datetime import timedelta

from app.utils.time import utcnow

from fastapi import APIRouter, Depends
from sqlmodel import Session, func, select

from app.auth import require_api_key
from app.database import get_session
from app.models import JobListing, JobStatus
from app.schemas import DashboardSummary

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"], dependencies=[Depends(require_api_key)])


@router.get("/summary", response_model=DashboardSummary)
def summary(session: Session = Depends(get_session)):
    total = session.exec(select(func.count(JobListing.id))).one()

    by_status = {}
    for status in JobStatus:
        count = session.exec(select(func.count(JobListing.id)).where(JobListing.status == status)).one()
        by_status[status.value] = count

    today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    new_today = session.exec(
        select(func.count(JobListing.id)).where(JobListing.fetched_at >= today_start)
    ).one()

    shortlisted_unapplied = session.exec(
        select(func.count(JobListing.id)).where(JobListing.status == JobStatus.shortlisted)
    ).one()

    week_ago = utcnow() - timedelta(days=7)
    applied_last_7_days = session.exec(
        select(func.count(JobListing.id)).where(
            JobListing.status.in_(
                [JobStatus.applied, JobStatus.interviewing, JobStatus.offer, JobStatus.rejected]
            ),
            JobListing.updated_at >= week_ago,
        )
    ).one()

    return DashboardSummary(
        total_jobs=total,
        by_status=by_status,
        new_today=new_today,
        shortlisted_unapplied=shortlisted_unapplied,
        applied_last_7_days=applied_last_7_days,
    )
