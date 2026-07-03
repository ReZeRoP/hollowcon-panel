# ⚡ Proxy Panel — Hysteria2 + VLESS

A lightweight **multi-protocol proxy panel** built with **FastAPI**. Manage clients
and generate ready-to-import share links, QR codes, config files, and a base64
**subscription** URL for three protocols:

| Protocol | Transport | Works on Render/Railway? | Best for |
|---|---|---|---|
| **Hysteria2** | UDP / QUIC | ❌ (no public UDP) | Fastest; VPS / Fly.io / Oracle |
| **VLESS-over-WebSocket** | TCP / HTTP(S) | ✅ **Yes** | Anywhere, incl. Render/Railway |
| **VLESS-over-TCP** | raw TCP | ❌ (not via HTTP edge) | VPS / direct host |

Every client automatically gets a Hysteria2 password **and** a VLESS UUID, so a
single subscription serves all three.

---

## ⚠️ How this works on Render / Railway (important)

Render and Railway expose only **one public HTTP/TCP port** and **no public UDP**.
This panel handles that cleanly:

- **Xray fronts the public `$PORT`** and multiplexes everything on one domain:
  - `VLESS-over-WebSocket` on your WS path  → **works** (rides the platform's HTTPS edge)
  - `VLESS-over-TCP` (raw)                  → not reachable through the HTTP edge
  - **everything else** (the dashboard, health checks) → falls back to the FastAPI panel
- **Hysteria2 (UDP)** can't run here — point `PUBLIC_HOST` at a UDP-capable host and
  run this same image there with `RUN_HYSTERIA=1`.

So on Render/Railway you get a working **VLESS-WS proxy + the management panel on the
same URL**. For the full trio (incl. Hysteria2 + VLESS-TCP), run it on a VPS.

```
client --TLS--> platform edge --plain--> :$PORT  (Xray VLESS/TCP inbound)
     ├─ VLESS-WS (path)  ── fallback ──▶ :10001  (Xray VLESS/WS inbound)
     ├─ VLESS-TCP (raw)  ── served directly (VPS)
     └─ anything else    ── fallback ──▶ :8000   (FastAPI panel)
```

---

## ✨ Features

- 🔐 Session-protected admin dashboard
- 👥 Add / enable / disable / delete clients (one identity → all 3 protocols)
- 🔗 Auto share links: `hysteria2://`, `vless://…type=ws`, `vless://…type=tcp`
- 📱 QR codes for every protocol (NekoBox, sing-box, v2rayNG, Streisand, Shadowrocket)
- 📄 Hysteria2 `config.yaml` download
- 📡 Base64 **subscription** endpoint (`/sub`) with all enabled links
- 🧩 Salamander obfuscation, HTTP masquerade, self-signed **or** Let's Encrypt TLS (Hysteria2)
- 🐳 One Docker image bundling the official **hysteria** and **xray** binaries
- 🚀 One-file deploy configs for Render (`render.yaml`) and Railway (`railway.json`)

---

## 🚀 Deploy on Render

1. Push this folder to a GitHub repo.
2. In Render: **New → Blueprint**, pick your repo (reads `render.yaml`).
3. Render auto-generates `ADMIN_PASSWORD` and `SECRET_KEY` (see the **Environment** tab).
4. Set **`PUBLIC_HOST`** to your Render domain (e.g. `proxy-panel.onrender.com`), then redeploy.
5. Open the URL, log in, add clients. Share the **VLESS-WS** link / QR — it works immediately.
   Use `/sub` as a subscription URL in your client app.

Defaults: `RUN_XRAY=1` (VLESS-WS on), `RUN_HYSTERIA=0` (no public UDP), `VLESS_TLS=1`.

## 🚀 Deploy on Railway

1. Push to GitHub. In Railway: **New Project → Deploy from GitHub repo** (uses `railway.json` + Dockerfile).
2. Set variables (**Variables** tab):
   ```
   RUN_XRAY=1
   RUN_HYSTERIA=0
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=<something strong>
   SECRET_KEY=<openssl rand -base64 32>
   PUBLIC_HOST=<your railway public domain>
   VLESS_WS_PATH=/vless-ws
   VLESS_PUBLIC_PORT=443
   VLESS_TLS=1
   ```
3. Generate a public domain under **Settings → Networking**. Add a **Volume** at `/data` to persist clients.

---

## 🌐 Run the full stack (Hysteria2 + VLESS) on a VPS

On any host where you control the ports (a $4/mo VPS, Fly.io, Oracle free tier, etc.):

```bash
git clone <your repo> && cd hysteria-panel   # folder name
cp .env.example .env      # edit values
docker compose up -d --build
```

`docker-compose.yml` exposes:
- `8080/tcp` → panel + **VLESS-WS** + **VLESS-TCP** (Xray front)
- `443/udp`  → **Hysteria2**

Open `http://<host>:8080`, log in, add clients. All three protocols work here.

### Real domain + Let's Encrypt (Hysteria2)
```
SELF_SIGNED=0
ACME_EMAIL=you@example.com
PUBLIC_HOST=proxy.yourdomain.com
```
For VLESS TLS on a VPS, terminate TLS with a reverse proxy (Caddy/Nginx) in front of
port 8080 and set `VLESS_TLS=1`; otherwise keep `VLESS_TLS=0` (plain WS/TCP).

---

## 🖥️ Run locally (dev)

```bash
pip install -r requirements.txt
cp .env.example .env
export RUN_HYSTERIA=0 RUN_XRAY=0 DATA_DIR=./data   # panel only, no binaries needed
uvicorn app.main:app --reload --port 8000
# http://localhost:8000  (login: admin / changeme)
```

---

## 📲 Client apps

Import via QR, a share link, or the subscription URL (`/sub`):

- **Android:** NekoBox, v2rayNG, Husi (all support Hysteria2 + VLESS)
- **iOS:** Streisand, Shadowrocket, Loon
- **Desktop:** NekoRay, sing-box, official `hysteria`/`xray` clients

Self-signed Hysteria2 links include `insecure=1`. For VLESS behind a real TLS edge
(Render/Railway), links use `security=tls` automatically.

---

## ⚙️ Environment variables

| Var | Default | Description |
|---|---|---|
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `changeme` | Panel login — **change it** |
| `SECRET_KEY` | random | Session cookie signing key |
| `PUBLIC_HOST` | — | Host/IP clients connect to |
| **Hysteria2** | | |
| `RUN_HYSTERIA` | `1` | Run the Hysteria2 (UDP) proxy in-container |
| `HYSTERIA_PORT` | `443` | UDP port |
| `OBFS_PASSWORD` | empty | Salamander obfuscation password |
| `MASQUERADE_URL` | HN | Site the server masquerades as |
| `SELF_SIGNED` / `ACME_EMAIL` | `1` / — | Self-signed vs Let's Encrypt TLS |
| **VLESS / Xray** | | |
| `RUN_XRAY` | `1` | Run Xray; fronts the public port for VLESS + panel |
| `VLESS_WS_PATH` | `/vless-ws` | WebSocket path for VLESS-WS |
| `VLESS_PUBLIC_PORT` | `443` | Port clients dial in links (edge TLS port) |
| `VLESS_TLS` | `1` | Client links use `security=tls` (behind edge TLS) |
| `VLESS_SNI` | `PUBLIC_HOST` | SNI / WS Host header |
| `PANEL_INTERNAL_PORT` | `8000` | Panel's internal port when Xray fronts |
| **Runtime** | | |
| `DATA_DIR` | `/data` | Persistent storage path |

---

## 🗂️ Project layout

```
hysteria-panel/
├── app/
│   ├── main.py          # FastAPI routes (dashboard, users, /sub, config previews)
│   ├── config.py        # env-driven settings
│   ├── db.py            # SQLite client store (+ VLESS UUID migration)
│   ├── hysteria.py      # Hysteria2 config, links, QR, process control
│   ├── xray.py          # VLESS (WS+TCP) config, links, process control
│   ├── auth.py          # admin session auth
│   ├── templates/       # Jinja2 dashboard/login/user pages
│   └── static/style.css # dark UI
├── Dockerfile           # panel + hysteria + xray binaries
├── docker-compose.yml   # full stack on a VPS
├── render.yaml          # Render blueprint (VLESS-WS + panel)
├── railway.json         # Railway deploy config
├── start.sh             # entrypoint (Xray-fronted vs panel-only)
└── requirements.txt
```

---

## 🔒 Security notes

- Change `ADMIN_PASSWORD` and set a strong `SECRET_KEY`.
- Prefer a real domain + TLS for the cleanest, most censorship-resistant setup.
- Keep the `/data` volume — it holds your client list, UUIDs, and certs.
- `/sub` is public by design (clients fetch it); it exposes credentials only for
  *enabled* clients. Disable/delete a client to revoke access instantly.
- The VLESS WebSocket transport shows a deprecation warning in newer Xray (migrating
  to XHTTP); it remains fully supported and is the most widely compatible transport.
