import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.routers import applications, dashboard, documents, jobs, profile, sources
from app.routers import settings as settings_router
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="JobHunter API",
    description=(
        "Personal job-search automation API: aggregates listings from multiple sources, "
        "scores them against your CV, and generates lightly-tailored CVs and cover letters. "
        "Single-user, API-key protected, backed by an embedded SQLite database -- no separate "
        "database server to deploy. See API_DOCUMENTATION.md for the full endpoint reference "
        "and LOVABLE_FRONTEND_BRIEF.md for how to build a frontend against this API."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router)
app.include_router(settings_router.router)
app.include_router(sources.router)
app.include_router(jobs.router)
app.include_router(documents.router)
app.include_router(applications.router)
app.include_router(dashboard.router)


@app.get("/api/health", tags=["Health"])
def health():
    return {"status": "ok"}
