"""FastAPI multi-protocol proxy panel: Hysteria2 + VLESS (WS & TCP)."""
from __future__ import annotations

import base64
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import (
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import auth, db, hysteria, xray
from .config import get_settings

BASE_DIR = os.path.dirname(__file__)
settings = get_settings()


def _reload_proxies() -> None:
    """Regenerate configs and restart whichever proxy engines are enabled."""
    hysteria.restart_hysteria()
    xray.restart_xray()


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    _reload_proxies()
    yield
    hysteria.stop_hysteria()
    xray.stop_xray()


app = FastAPI(title="Proxy Panel", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# --------------------------------------------------------------------------- #
# Link helpers
# --------------------------------------------------------------------------- #
def client_links(user: dict) -> dict[str, str]:
    """All share links for a client, keyed by protocol."""
    return {
        "hysteria2": hysteria.client_uri(user),
        "vless_ws": xray.vless_ws_uri(user),
        "vless_tcp": xray.vless_tcp_uri(user),
    }


def build_subscription() -> str:
    """Base64 subscription combining every enabled client's protocol links."""
    lines: list[str] = []
    for u in db.list_users():
        if not u["enabled"]:
            continue
        links = client_links(u)
        lines.append(links["hysteria2"])
        lines.append(links["vless_ws"])
        lines.append(links["vless_tcp"])
    return base64.b64encode("\n".join(lines).encode()).decode()


# --------------------------------------------------------------------------- #
# Health & auth
# --------------------------------------------------------------------------- #
@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return "ok"


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if auth.is_authenticated(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if auth.check_credentials(username, password):
        request.session["user"] = username
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(
        request, "login.html", {"error": "Invalid credentials"}, status_code=401
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    guard = auth.require_login(request)
    if guard:
        return guard
    users = db.list_users()
    ctx = {
        "users": users,
        "settings": settings,
        "hy_available": hysteria.hysteria_available(),
        "hy_running": hysteria.is_running(),
        "xray_available": xray.xray_available(),
        "xray_running": xray.is_running(),
        "sub_url": str(request.base_url) + "sub",
    }
    return templates.TemplateResponse(request, "dashboard.html", ctx)


@app.post("/users/create")
def users_create(request: Request, name: str = Form(...), note: str = Form("")):
    guard = auth.require_login(request)
    if guard:
        return guard
    name = name.strip()
    if name and not db.get_user_by_name(name):
        db.create_user(name=name, note=note.strip())
        _reload_proxies()
    return RedirectResponse("/", status_code=302)


@app.post("/users/{user_id}/toggle")
def users_toggle(request: Request, user_id: int):
    guard = auth.require_login(request)
    if guard:
        return guard
    db.toggle_user(user_id)
    _reload_proxies()
    return RedirectResponse("/", status_code=302)


@app.post("/users/{user_id}/delete")
def users_delete(request: Request, user_id: int):
    guard = auth.require_login(request)
    if guard:
        return guard
    db.delete_user(user_id)
    _reload_proxies()
    return RedirectResponse("/", status_code=302)


@app.get("/users/{user_id}", response_class=HTMLResponse)
def user_detail(request: Request, user_id: int):
    guard = auth.require_login(request)
    if guard:
        return guard
    user = db.get_user(user_id)
    if not user:
        return RedirectResponse("/", status_code=302)
    links = client_links(user)
    protocols = [
        {
            "key": "hysteria2",
            "label": "Hysteria2 (UDP / QUIC)",
            "note": "Fastest. Needs a UDP-capable host (VPS/Fly.io) — not Render/Railway.",
            "uri": links["hysteria2"],
            "qr": hysteria.qr_data_uri(links["hysteria2"]),
            "config": hysteria.client_config_yaml(user),
            "config_lang": "yaml",
        },
        {
            "key": "vless_ws",
            "label": "VLESS over WebSocket",
            "note": "Rides HTTP/TLS — works on Render, Railway, and any host.",
            "uri": links["vless_ws"],
            "qr": hysteria.qr_data_uri(links["vless_ws"]),
            "config": None,
            "config_lang": None,
        },
        {
            "key": "vless_tcp",
            "label": "VLESS over TCP",
            "note": "Raw TCP. Best on a VPS/direct host (not the HTTP edge).",
            "uri": links["vless_tcp"],
            "qr": hysteria.qr_data_uri(links["vless_tcp"]),
            "config": None,
            "config_lang": None,
        },
    ]
    ctx = {"user": user, "protocols": protocols}
    return templates.TemplateResponse(request, "user.html", ctx)


@app.get("/users/{user_id}/config.yaml", response_class=PlainTextResponse)
def user_config(request: Request, user_id: int):
    guard = auth.require_login(request)
    if guard:
        return guard
    user = db.get_user(user_id)
    if not user:
        return PlainTextResponse("not found", status_code=404)
    return PlainTextResponse(hysteria.client_config_yaml(user))


# --------------------------------------------------------------------------- #
# Public subscription endpoint (base64 list of all enabled protocol URIs)
# --------------------------------------------------------------------------- #
@app.get("/sub", response_class=PlainTextResponse)
def subscription():
    return Response(
        content=build_subscription(),
        media_type="text/plain; charset=utf-8",
        headers={"Profile-Update-Interval": "12"},
    )


# --------------------------------------------------------------------------- #
# Server config previews + control
# --------------------------------------------------------------------------- #
@app.get("/server-config.yaml", response_class=PlainTextResponse)
def server_config(request: Request):
    guard = auth.require_login(request)
    if guard:
        return guard
    import yaml

    return PlainTextResponse(yaml.safe_dump(hysteria.build_server_config(), sort_keys=False))


@app.get("/xray-config.json", response_class=PlainTextResponse)
def xray_config(request: Request):
    guard = auth.require_login(request)
    if guard:
        return guard
    return PlainTextResponse(json.dumps(xray.build_server_config(), indent=2))


@app.post("/server/restart")
def server_restart(request: Request):
    guard = auth.require_login(request)
    if guard:
        return guard
    _reload_proxies()
    return RedirectResponse("/", status_code=302)
