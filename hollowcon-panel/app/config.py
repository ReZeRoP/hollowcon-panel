"""Application settings loaded from environment variables."""
from __future__ import annotations

import os
import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Admin panel auth ---
    admin_username: str = "admin"
    admin_password: str = "changeme"
    # Session signing key. Auto-generated if not provided (regenerated on restart).
    secret_key: str = secrets.token_urlsafe(32)

    # --- Public connection info (used to build client links) ---
    # The domain/IP clients connect to for the Hysteria2 proxy.
    # On a UDP-capable host this is your server's hostname/IP.
    public_host: str = "your-server.example.com"
    # UDP port Hysteria2 listens on for proxy traffic.
    hysteria_port: int = 443

    # --- Hysteria2 server behaviour ---
    # obfuscation salamander password (optional but recommended). Empty = disabled.
    obfs_password: str = ""
    # Masquerade URL - hysteria pretends to be this site to probers.
    masquerade_url: str = "https://news.ycombinator.com/"
    # Up/down speed hints advertised to clients (Mbps). 0 = unlimited/BBR.
    up_mbps: int = 0
    down_mbps: int = 0

    # TLS: use ACME (Let's Encrypt) when a real domain is set, else self-signed.
    acme_email: str = ""
    # Set to "1" to force self-signed certs (insecure clients required).
    self_signed: str = "1"

    # --- Storage ---
    data_dir: str = os.getenv("DATA_DIR", "/data")

    # Path to the hysteria binary inside the container.
    hysteria_bin: str = os.getenv("HYSTERIA_BIN", "/usr/local/bin/hysteria")

    # Whether this instance should try to run the hysteria server process.
    # On Render/Railway (TCP-only) set to "0" and use the panel only.
    run_hysteria: str = os.getenv("RUN_HYSTERIA", "1")

    # --- VLESS / Xray (VLESS-over-WebSocket + VLESS-over-TCP) ---
    # WS works on Render/Railway (rides their HTTP/TLS edge); TCP is VPS/direct.
    run_xray: str = os.getenv("RUN_XRAY", "1")
    xray_bin: str = os.getenv("XRAY_BIN", "/usr/local/bin/xray")

    # WebSocket path clients use for VLESS-WS.
    vless_ws_path: str = os.getenv("VLESS_WS_PATH", "/vless-ws")
    # Port clients dial in the generated links (443 = platform TLS edge port).
    vless_public_port: int = int(os.getenv("VLESS_PUBLIC_PORT", "443"))
    # "1" => client links use security=tls (behind Render/Railway/edge TLS).
    vless_tls: str = os.getenv("VLESS_TLS", "1")
    # SNI/Host for VLESS TLS + WS Host header. Defaults to public_host if empty.
    vless_sni: str = os.getenv("VLESS_SNI", "")

    # Public TCP port Xray binds inside the container (the platform maps $PORT
    # to this). When Xray fronts the panel, this is the single public port.
    front_port: int = int(os.getenv("PORT", "8080"))
    # Panel's internal port when Xray fronts the public port.
    panel_internal_port: int = int(os.getenv("PANEL_INTERNAL_PORT", "8000"))
    # Loopback port for the VLESS-WS inbound behind the TCP fallback.
    xray_ws_internal_port: int = int(os.getenv("XRAY_WS_INTERNAL_PORT", "10001"))

    @property
    def effective_sni(self) -> str:
        return self.vless_sni or self.public_host

    @property
    def db_path(self) -> str:
        os.makedirs(self.data_dir, exist_ok=True)
        return os.path.join(self.data_dir, "panel.db")

    @property
    def server_config_path(self) -> str:
        os.makedirs(self.data_dir, exist_ok=True)
        return os.path.join(self.data_dir, "hysteria-server.yaml")

    @property
    def xray_config_path(self) -> str:
        os.makedirs(self.data_dir, exist_ok=True)
        return os.path.join(self.data_dir, "xray-config.json")


@lru_cache
def get_settings() -> Settings:
    return Settings()
