"""VLESS (Xray-core) support: server config, share links, and process control.

Topology (single public TCP port, works behind Render/Railway TLS edge):

    client --TLS--> platform edge --plain--> :front_port  (Xray VLESS/TCP inbound)
        |                                          |
        |  VLESS-TCP (raw)  -> handled here direct |
        |  VLESS-WS  (path) -> fallback -> :ws_port (Xray VLESS/WS inbound)
        |  anything else    -> fallback -> :panel  (FastAPI panel)

* VLESS-over-WebSocket rides the platform's HTTP/TLS edge  -> works on Render/Railway.
* VLESS-over-TCP is raw TCP  -> works on a VPS / UDP-or-TCP capable host, not the HTTP edge.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import urllib.parse
from typing import Optional

from .config import get_settings
from . import db

_proc: Optional[subprocess.Popen] = None


# --------------------------------------------------------------------------- #
# Server config generation (Xray config.json)
# --------------------------------------------------------------------------- #
def _clients() -> list[dict]:
    return [
        {"id": u["uuid"], "email": u["name"], "level": 0}
        for u in db.list_users()
        if u["enabled"] and u["uuid"]
    ]


def build_server_config() -> dict:
    """Build an Xray config.json with a VLESS TCP inbound that falls back to
    the VLESS-WS inbound (by path) and to the FastAPI panel (default)."""
    s = get_settings()
    clients = _clients()

    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                # Public front door. Real VLESS-TCP clients are served directly;
                # WS + browser traffic is dispatched via fallbacks.
                "tag": "vless-front",
                "listen": "0.0.0.0",
                "port": s.front_port,
                "protocol": "vless",
                "settings": {
                    "clients": clients,
                    "decryption": "none",
                    "fallbacks": [
                        # VLESS-over-WebSocket -> internal WS inbound.
                        {"path": s.vless_ws_path, "dest": s.xray_ws_internal_port},
                        # Everything else (browser, health checks) -> the panel.
                        {"dest": s.panel_internal_port},
                    ],
                },
                "streamSettings": {"network": "tcp", "security": "none"},
            },
            {
                # Internal VLESS-over-WebSocket inbound (loopback only).
                "tag": "vless-ws",
                "listen": "127.0.0.1",
                "port": s.xray_ws_internal_port,
                "protocol": "vless",
                "settings": {"clients": clients, "decryption": "none"},
                "streamSettings": {
                    "network": "ws",
                    "security": "none",
                    "wsSettings": {"path": s.vless_ws_path},
                },
            },
        ],
        "outbounds": [
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "block"},
        ],
    }


def write_server_config() -> str:
    s = get_settings()
    path = s.xray_config_path
    with open(path, "w") as f:
        json.dump(build_server_config(), f, indent=2)
    return path


# --------------------------------------------------------------------------- #
# Client share links (vless://...)
# --------------------------------------------------------------------------- #
def _security() -> str:
    return "tls" if get_settings().vless_tls == "1" else "none"


def vless_ws_uri(user: dict) -> str:
    """VLESS-over-WebSocket share link (works on Render/Railway)."""
    s = get_settings()
    params = {
        "type": "ws",
        "encryption": "none",
        "security": _security(),
        "path": s.vless_ws_path,
        "host": s.effective_sni,
    }
    if _security() == "tls":
        params["sni"] = s.effective_sni
    query = urllib.parse.urlencode(params)
    frag = urllib.parse.quote(f"{user['name']}-ws")
    return f"vless://{user['uuid']}@{s.public_host}:{s.vless_public_port}?{query}#{frag}"


def vless_tcp_uri(user: dict) -> str:
    """VLESS-over-TCP share link (raw TCP; use on a VPS/direct host)."""
    s = get_settings()
    params = {
        "type": "tcp",
        "encryption": "none",
        # Raw TCP behind Xray security=none. Set VLESS_TLS handled at edge only.
        "security": "none",
    }
    query = urllib.parse.urlencode(params)
    frag = urllib.parse.quote(f"{user['name']}-tcp")
    return f"vless://{user['uuid']}@{s.public_host}:{s.vless_public_port}?{query}#{frag}"


# --------------------------------------------------------------------------- #
# Process control
# --------------------------------------------------------------------------- #
def xray_available() -> bool:
    s = get_settings()
    return s.run_xray == "1" and os.path.exists(s.xray_bin)


def is_running() -> bool:
    return _proc is not None and _proc.poll() is None


def restart_xray() -> str:
    global _proc
    s = get_settings()
    if not xray_available():
        return "disabled"

    write_server_config()

    if is_running():
        _proc.send_signal(signal.SIGTERM)  # type: ignore[union-attr]
        try:
            _proc.wait(timeout=5)  # type: ignore[union-attr]
        except Exception:
            _proc.kill()  # type: ignore[union-attr]

    _proc = subprocess.Popen([s.xray_bin, "run", "-c", s.xray_config_path])
    return "running"


def stop_xray() -> None:
    global _proc
    if is_running():
        _proc.terminate()  # type: ignore[union-attr]
    _proc = None
