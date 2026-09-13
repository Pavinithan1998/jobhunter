"""
Thin wrapper around the Anthropic SDK, shared by the relevance-scoring and
CV/cover-letter tailoring services.
"""
from anthropic import Anthropic

from app.config import get_settings


class LLMNotConfigured(Exception):
    pass


def get_client() -> Anthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise LLMNotConfigured(
            "ANTHROPIC_API_KEY is not set in .env. Relevance scoring and "
            "document tailoring both require it."
        )
    return Anthropic(api_key=settings.anthropic_api_key)


def get_model() -> str:
    return get_settings().anthropic_model
