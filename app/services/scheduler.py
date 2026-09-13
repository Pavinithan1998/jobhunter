"""
Runs fetch + score automatically once a day (time configurable via
DAILY_FETCH_HOUR / DAILY_FETCH_MINUTE in .env), so the "filter new jobs at
the end of the day" workflow happens without you triggering it manually.

You can still call POST /api/jobs/fetch and POST /api/jobs/score-batch by
hand any time -- the scheduler just does the same thing on a timer.
"""
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import Session

from app.config import get_settings
from app.database import engine
from app.services.aggregator import run_fetch
from app.services.matching import score_pending_jobs

logger = logging.getLogger("jobhunter.scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _daily_job() -> None:
    logger.info("Running scheduled daily fetch + score")
    with Session(engine) as session:
        fetch_result = await run_fetch(session)
        logger.info("Daily fetch: %s", fetch_result)
        score_result = score_pending_jobs(session)
        logger.info("Daily scoring: %s", score_result)


def start_scheduler() -> None:
    global _scheduler
    settings = get_settings()
    if not settings.enable_scheduler:
        logger.info("Scheduler disabled via ENABLE_SCHEDULER=false")
        return

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        lambda: asyncio.create_task(_daily_job()),
        "cron",
        hour=settings.daily_fetch_hour,
        minute=settings.daily_fetch_minute,
        id="daily_fetch_and_score",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started: daily fetch+score at %02d:%02d",
        settings.daily_fetch_hour,
        settings.daily_fetch_minute,
    )


def stop_scheduler() -> None:
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
