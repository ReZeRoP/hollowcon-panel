"""Simple session-cookie admin auth."""
from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.responses import RedirectResponse

from .config import get_settings


def check_credentials(username: str, password: str) -> bool:
    s = get_settings()
    return hmac.compare_digest(username, s.admin_username) and hmac.compare_digest(
        password, s.admin_password
    )


def is_authenticated(request: Request) -> bool:
    return request.session.get("user") == get_settings().admin_username


def require_login(request: Request) -> RedirectResponse | None:
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    return None
