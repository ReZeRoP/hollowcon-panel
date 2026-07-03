# ---- Hysteria2 Panel image ----
# Includes the FastAPI panel AND the official hysteria2 binary so the same
# image can run the real proxy on a UDP-capable host (VPS, Fly.io, Oracle...).
FROM python:3.12-slim

# openssl for self-signed certs; ca-certificates for ACME/TLS; unzip for xray.
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*

# Install the official hysteria2 binary.
# Pin a version for reproducible builds; bump as needed.
ARG HYSTERIA_VERSION=v2.6.1
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) hy_arch="amd64" ;; \
      arm64) hy_arch="arm64" ;; \
      *) hy_arch="amd64" ;; \
    esac; \
    curl -fsSL -o /usr/local/bin/hysteria \
      "https://github.com/apernet/hysteria/releases/download/app/${HYSTERIA_VERSION}/hysteria-linux-${hy_arch}"; \
    chmod +x /usr/local/bin/hysteria; \
    /usr/local/bin/hysteria version || true

# Install the official Xray-core binary (VLESS: WebSocket + TCP).
ARG XRAY_VERSION=v25.6.8
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) xr_zip="Xray-linux-64.zip" ;; \
      arm64) xr_zip="Xray-linux-arm64-v8a.zip" ;; \
      *) xr_zip="Xray-linux-64.zip" ;; \
    esac; \
    curl -fsSL -o /tmp/xray.zip \
      "https://github.com/XTLS/Xray-core/releases/download/${XRAY_VERSION}/${xr_zip}"; \
    unzip -o /tmp/xray.zip xray -d /usr/local/bin; \
    chmod +x /usr/local/bin/xray; \
    rm -f /tmp/xray.zip; \
    /usr/local/bin/xray version || true

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x start.sh

# Persistent data (SQLite DB, certs, generated server config).
ENV DATA_DIR=/data
RUN mkdir -p /data
VOLUME ["/data"]

# Panel port (overridden by $PORT on Render/Railway).
EXPOSE 8000
# Hysteria2 UDP proxy port (only reachable on UDP-capable hosts).
EXPOSE 443/udp
# VLESS front port (panel + VLESS-WS + VLESS-TCP multiplexed here).
EXPOSE 8080

CMD ["./start.sh"]
