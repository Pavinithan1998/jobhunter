"""
Central configuration. Everything is loaded from environment variables / a
local .env file so the whole app can be reconfigured without touching code.
"""
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
DOCS_DIR = STORAGE_DIR / "documents"
UPLOADS_DIR = STORAGE_DIR / "uploads"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Security -----------------------------------------------------
    # Single-user app: every request must send this value in the
    # `X-API-Key` header. Set your own random string in .env.
    api_key: str = "changeme-set-a-real-key-in-env"

    # Comma-separated list of origins allowed to call this API from a
    # browser (your Lovable-built frontend's URL, plus localhost for dev).
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # --- Storage --------------------------------------------------------
    database_url: str = f"sqlite:///{STORAGE_DIR / 'jobhunter.db'}"

    # --- LLM (tailoring + relevance scoring) ----------------------------
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-6"

    # --- Job source connectors ------------------------------------------
    adzuna_app_id: Optional[str] = None
    adzuna_app_key: Optional[str] = None
    adzuna_country: str = "gb"  # gb, us, etc.

    jooble_api_key: Optional[str] = None

    # Free tier at https://serpapi.com/ -- powers the on-demand "search the
    # internet for jobs" endpoint (POST /api/jobs/search-web).
    serpapi_key: Optional[str] = None

    # Optional manual override: the direct CSV download URL for the UK
    # Home Office's public register of licensed Worker/Temporary Worker
    # sponsors. Normally the app finds this automatically by reading
    # https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers
    # and following the CSV link on that page, but gov.uk occasionally
    # restructures that page -- if auto-discovery ever breaks, paste the
    # current CSV link here (right-click "Download the list" -> copy link)
    # as a working fallback.
    uk_sponsor_register_csv_url: Optional[str] = None

    # --- Scheduler --------------------------------------------------------
    enable_scheduler: bool = True
    daily_fetch_hour: int = 18  # 24h clock, server-local time
    daily_fetch_minute: int = 0

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
