"""Hysteria2 server-config generation, client link/URI building, and process control."""
from __future__ import annotations

import base64
import io
import os
import signal
import subprocess
import urllib.parse
from typing import Optional

import qrcode
import yaml

from .config import get_settings
from . import db

_proc: Optional[subprocess.Popen] = None


# --------------------------------------------------------------------------- #
# Server config generation
# --------------------------------------------------------------------------- #
def build_server_config() -> dict:
    """Build a hysteria2 server config dict from settings + enabled users."""
    s = get_settings()
    passwords = db.enabled_auth_passwords()

    config: dict = {
        "listen": f":{s.hysteria_port}",
        # Authenticate clients whose password is in our userlist.
        "auth": {
            "type": "userpass",
            # hysteria2 userpass expects {username: password}. We use the
            # client name as username and its auth_password as password.
            "userpass": {
                u["name"]: u["auth_password"]
                for u in db.list_users()
                if u["enabled"]
            },
        },
        "masquerade": {
            "type": "proxy",
            "proxy": {"url": s.masquerade_url, "rewriteHost": True},
        },
    }

    # TLS: ACME for a real domain, otherwise self-signed generated at start.
    if s.self_signed == "1" or not s.acme_email:
        config["tls"] = {
            "cert": os.path.join(s.data_dir, "cert.crt"),
            "key": os.path.join(s.data_dir, "cert.key"),
        }
    else:
        config["acme"] = {
            "domains": [s.public_host],
            "email": s.acme_email,
        }

    if s.obfs_password:
        config["obfs"] = {
            "type": "salamander",
            "salamander": {"password": s.obfs_password},
        }

    if s.up_mbps or s.down_mbps:
        config["bandwidth"] = {
            "up": f"{s.up_mbps} mbps" if s.up_mbps else "0",
            "down": f"{s.down_mbps} mbps" if s.down_mbps else "0",
        }

    return config


def write_server_config() -> str:
    s = get_settings()
    cfg = build_server_config()
    path = s.server_config_path
    with open(path, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    return path


# --------------------------------------------------------------------------- #
# Client config / share URI / QR
# --------------------------------------------------------------------------- #
def client_uri(user: dict) -> str:
    """Build a hysteria2:// share URI for a client (sing-box / nekoray / v2rayN)."""
    s = get_settings()
    # userpass auth -> the credential is "username:password"
    cred = f"{user['name']}:{user['auth_password']}"
    netloc = f"{urllib.parse.quote(cred, safe='')}@{s.public_host}:{s.hysteria_port}"

    params: dict[str, str] = {}
    if s.obfs_password:
        params["obfs"] = "salamander"
        params["obfs-password"] = s.obfs_password
    if s.self_signed == "1" or not s.acme_email:
        params["insecure"] = "1"
    params["sni"] = s.public_host

    query = urllib.parse.urlencode(params)
    frag = urllib.parse.quote(user["name"])
    return f"hysteria2://{netloc}/?{query}#{frag}"


def client_config_yaml(user: dict) -> str:
    """Full hysteria2 client config.yaml for the official client."""
    s = get_settings()
    cfg: dict = {
        "server": f"{s.public_host}:{s.hysteria_port}",
        "auth": f"{user['name']}:{user['auth_password']}",
        "tls": {"sni": s.public_host, "insecure": s.self_signed == "1"},
        "socks5": {"listen": "127.0.0.1:1080"},
        "http": {"listen": "127.0.0.1:8080"},
    }
    if s.obfs_password:
        cfg["obfs"] = {
            "type": "salamander",
            "salamander": {"password": s.obfs_password},
        }
    return yaml.safe_dump(cfg, sort_keys=False)


def qr_data_uri(text: str) -> str:
    """Return a base64 PNG data URI of the QR code for `text`."""
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def subscription_body() -> str:
    """Base64 subscription containing all enabled client URIs (v2ray style)."""
    uris = [client_uri(u) for u in db.list_users() if u["enabled"]]
    joined = "\n".join(uris)
    return base64.b64encode(joined.encode()).decode()


# --------------------------------------------------------------------------- #
# Process control (only when RUN_HYSTERIA=1 and binary exists)
# --------------------------------------------------------------------------- #
def _ensure_self_signed_cert() -> None:
    s = get_settings()
    crt = os.path.join(s.data_dir, "cert.crt")
    key = os.path.join(s.data_dir, "cert.key")
    if os.path.exists(crt) and os.path.exists(key):
        return
    subprocess.run(
        [
            "openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048",
            "-keyout", key, "-out", crt, "-days", "3650",
            "-subj", f"/CN={s.public_host}",
        ],
        check=False,
    )


def hysteria_available() -> bool:
    s = get_settings()
    return s.run_hysteria == "1" and os.path.exists(s.hysteria_bin)


def is_running() -> bool:
    return _proc is not None and _proc.poll() is None


def restart_hysteria() -> str:
    """(Re)write config and restart the hysteria server process."""
    global _proc
    s = get_settings()
    if not hysteria_available():
        return "disabled"

    if s.self_signed == "1" or not s.acme_email:
        _ensure_self_signed_cert()

    write_server_config()

    if is_running():
        _proc.send_signal(signal.SIGTERM)  # type: ignore[union-attr]
        try:
            _proc.wait(timeout=5)  # type: ignore[union-attr]
        except Exception:
            _proc.kill()  # type: ignore[union-attr]

    _proc = subprocess.Popen(
        [s.hysteria_bin, "server", "-c", s.server_config_path]
    )
    return "running"


def stop_hysteria() -> None:
    global _proc
    if is_running():
        _proc.terminate()  # type: ignore[union-attr]
    _proc = None
