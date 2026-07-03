#!/usr/bin/env sh
set -e

# ---------------------------------------------------------------------------
# Port strategy
# ---------------------------------------------------------------------------
# When VLESS/Xray is enabled it FRONTS the public port and multiplexes:
#   * VLESS-TCP   -> served directly
#   * VLESS-WS    -> fallback by path
#   * everything else (the panel, health checks) -> FastAPI on the internal port
# When Xray is disabled, the FastAPI panel binds the public port directly.
# ---------------------------------------------------------------------------

PUBLIC_PORT="${PORT:-8080}"
INTERNAL_PORT="${PANEL_INTERNAL_PORT:-8000}"

if [ "${RUN_XRAY:-1}" = "1" ]; then
  PANEL_HOST="127.0.0.1"
  PANEL_PORT="${INTERNAL_PORT}"
  echo "==> Xray fronts :${PUBLIC_PORT}; panel internal on ${PANEL_HOST}:${PANEL_PORT}"
else
  PANEL_HOST="0.0.0.0"
  PANEL_PORT="${PUBLIC_PORT}"
  echo "==> Panel-only mode on ${PANEL_HOST}:${PANEL_PORT}"
fi

# The panel process itself launches the hysteria/xray subprocesses on startup
# (see app.main lifespan), so we only need to run uvicorn here.
exec uvicorn app.main:app --host "${PANEL_HOST}" --port "${PANEL_PORT}" --workers 1
