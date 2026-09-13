"""
Single-user API key authentication.

Every protected endpoint depends on `require_api_key`. The frontend must
send the configured key on every request as:

    X-API-Key: <your key>

This is deliberately simple (no OAuth, no user table) because this app is
built for one person managing their own job search, not a multi-tenant
product.
"""
from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_api_key(x_api_key: str = Header(..., description="Your personal API key")) -> None:
    settings = get_settings()
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Send it as the 'X-API-Key' header.",
        )
