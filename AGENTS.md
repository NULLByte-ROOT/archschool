# PROJECT CONTEXT: ArchSchool — SINGLE SOURCE OF TRUTH

You are working on a production-ready project named **ArchSchool**. This file is the single source of truth for all future AI sessions. Read this entire context carefully before writing any code.

## 1. Project Overview
ArchSchool is a social-network-style school workspace for a class team (11th grade). It manages assignments, timetables, chats, and gamification (points/leaderboard). The UI is strictly RTL (Persian) and uses a dark/light theme system.

## 2. Tech Stack
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4, Framer Motion, Lucide React, Recharts.
- **Backend:** FastAPI (Python 3.12+), SQLAlchemy, Pydantic v2, PyJWT, psycopg (for PostgreSQL).
- **Database:** PostgreSQL (Production).
- **Containerization:** Docker & Docker Compose.

## 3. Server & Infrastructure (CRITICAL)
- **Host OS:** Linux (Ubuntu/Debian) accessed via SSH. The server is SHARED with other projects (like Pasarguard).
- **Domain:** `https://archschool.vidxsepehr.ir`
- **Ports:** 
  - Host Nginx runs on 80/443 (handles SSL via Certbot).
  - Host Nginx proxies to the `archschool_app` upstream, which points at the active blue-green slot: `127.0.0.1:6241` (blue) or `127.0.0.1:6242` (green).
  - Both slot ports are bound to loopback only.
  - PostgreSQL is strictly internal to Docker (no host port exposed) to avoid conflicting with the server's existing databases.
- **Docker Containers:** `archschool_db`, `archschool_backend_blue`, `archschool_frontend_blue`, `archschool_backend_green`, `archschool_frontend_green`. Only one slot runs at a time (the other is kept stopped for rollback).
- **Host Nginx Config:** Located at `/etc/nginx/sites-available/archschool`. Requires `client_max_body_size 30m;` and WebSocket headers (`Upgrade`, `Connection "upgrade"`) inside the `location /` block. Its `proxy_pass` must point at `http://archschool_app` (managed in `/etc/nginx/conf.d/00-archschool-upstream.conf`).
- **Docker Nginx:** Inside the frontend container, `/api` and `/api/ws` routes must be marked as `location ^~ /api/` to prevent regex static file rules from hijacking image URLs. `frontend/nginx.conf.template` is rendered at container start; `BACKEND_HOST` is injected per slot by Compose.

## 4. Authentication & Roles (RBAC) — EXACT RULES
- **Access Code Only:** There are no passwords. Authentication is done via `username` + a **6-character alphanumeric uppercase Access Code** (`^[A-Z0-9]{6}$`, e.g. `ROOT01`).
- **Roles:** There are **3 assignable roles** (`admin`, `friend`, `member`) and **1 special account** (`owner`). The legacy `editor` role is retired (boot migration converts those accounts to `admin`).
- **Permissions (exact):**
  - **Everyone (all roles):** Can toggle assignment completion ("Done"/"Read"), appear in Team Status and the Leaderboard, and view assignments.
  - **Member:** Cannot chat (global/DM locked — «برای دسترسی به گفتگو، از ادمین اجازه بگیرید.»). Cannot create/edit assignments. CAN view attachments. CAN leave comments on assignments (only inside assignment comment rooms; enforced in REST `messages.py` and WS `ws.py`).
  - **Friend:** CAN chat (global, DM, assignment comments). CAN view and comment on assignments. Cannot create/edit assignments. Cannot delete chat messages — not even their own.
  - **Admin:** Has all Friend capabilities + CAN create/edit/delete assignments + CAN delete ANY chat message and clear rooms.
  - **Owner (special account):** Has all Admin capabilities + CAN view server stats (`/api/server-stats`, psutil polling on the `ServerStatsPage`) + CAN change the access code of any user (`PATCH /api/users/{user_id}/code` — Owner-only endpoint).
- **Owner account:** Bootstrapped from `backend/.env` keys `OWNER_USERNAME` / `OWNER_ACCESS_CODE` by `_ensure_owner_account()` in `main.py`, which **re-applies the env code at every boot** — the `.env` is the source of truth for the Owner's OWN code. The Owner's own code therefore must be changed via the server (menu option `14) Set Owner Credentials`), and `PATCH /api/users/{id}/code` returns «کد حساب Owner از backend/.env کنترل می‌شود؛ از منوی سرور تغییر دهید» if the Owner tries to change their own code while an env code is set. Codes for all OTHER users are changed only through the Owner-only endpoint / the Users page "Change Code" button (visible to Owner only).
- **Role management:** Done on the `/rootvoid` Users page by admin/owner. Only an Owner can mint another Owner.
- **Chat implementation notes:** `is_staff` = admin/owner (assignment CRUD, message deletion, room clearing). Message deletion is staff-only; friends never get a delete button in the UI. Comments on an assignment live in the embedded `ChatRoom room=assignment:<id>` on the assignment detail page, where members are allowed to write; the `/chat` page itself remains blocked for members.
- **Number formatting rule:** ALL dynamic numbers in the UI use Latin (English) digits. Persian calendar dates use locale `"fa-IR-u-nu-latn"` (Persian wording/months, Latin digits); pure numbers/bytes/counters use `"en-US"` `Intl.NumberFormat`. Never use bare `"fa-IR"` locales or Persian digit converters in new code.

## 5. Deployment Workflow & Scripts
- **GitHub Repo:** `https://github.com/NULLByte-ROOT/archschool` (Branch: `main`).
- **Deployment Script:** `./deploy.sh` on the server — blue-green. `./deploy.sh deploy` pulls, builds the inactive slot, verifies it, switches the host Nginx upstream and soaks; `rollback`, `cleanup`, `status`, `fix-nginx` are the other subcommands. NEVER use `docker compose up -d`/`down`/`--remove-orphans` directly: slots are Compose profiles and the database is shared.
- **Interactive menu:** Running `./deploy.sh` with no args opens the menu; option **`14) Set Owner Credentials (Username & Access Code)`** prompts for a username and a 6-char uppercase access code, writes `OWNER_USERNAME`/`OWNER_ACCESS_CODE` into `backend/.env`, then offers to restart the backend to apply.
- **Host Nginx WebSocket:** `deploy.sh` detects the headers by content, per location — never by a marker comment, so a hand-written block is never touched. It only inserts the block into a proxying location that lacks the headers; `location /` upgrading does not help when a more specific `location ^~ /api/` also proxies, because `/api/ws` takes that branch, arrives at FastAPI as a plain GET and answers 404. The injected block sets `proxy_http_version 1.1`, `Upgrade $http_upgrade`, `Connection "upgrade"` and long timeouts. `./deploy.sh fix-nginx` repairs it in place (no rebuild) and restarts Nginx. The public WS probe uses `curl --http1.1` and accepts `101/400/401/403/426` — upgrades do not exist in HTTP/2, so without `--http1.1` the probe gets a false 404.
- **WebSocket handshake:** `backend/app/routers/ws.py` accepts the socket *first* and then closes with `1008` for a bad token/room. A close before `accept()` becomes a failed HTTP handshake, which browsers can only report as `1006` with no reason; `logging.basicConfig` is configured in `main.py` so the `ws handshake room=… token=present|MISSING host=…` line is actually printed.
- **Traffic switch:** after rewriting `/etc/nginx/conf.d/00-archschool-upstream.conf`, `deploy.sh` runs `systemctl restart nginx` (not reload) so old workers cannot keep serving the previous slot, and verifies the public URL reports the new revision (one retry with an extra restart, then rollback).
- **Database Migrations:** Handled automatically via `Base.metadata.create_all` and custom `_ensure_columns()` logic in `main.py`. Explicit SQL scripts are in `backend/migrations/` (safe to run idempotently).
- **Backup / Restore:** `./deploy.sh backup` writes `archschool_backup_YYYY-MM-DD_HH-MM.tar.gz` in the project root (mode 600: `database.sql`, `uploads.tar.gz`, `.env`, `metadata.txt`). `./deploy.sh restore <archive>` restores on a fresh or existing server (confirmation required) and finishes with a standard deploy. Also `./deploy.sh list-backups`, `deploy --backup`, `--out=DIR`. Archives are git-ignored — never commit them.

## 6. Core Features Implemented
- **Dashboard:** CTA, activity charts, recent chats, upcoming deadlines.
- **Timetable:** Sat-Wed (4 periods, 08:00-14:00), live countdown, next-day preview; `/admin/bells` bell-schedule editor.
- **Assignments:** Public/shared. Grouped by Urgent/Upcoming/Completed. File attachments (with uploader attribution & delete button). Task-specific comment rooms on the detail page.
- **Chat:** Telegram-style UI. WebSocket for real-time. Global, Private (DM), and Assignment rooms. Staff (admin/owner) can delete any message or clear rooms. Full-screen avatar viewer & Telegram-style profile modal; swipe-to-reply.
- **Server Stats:** Owner-only page (CPU/RAM/net gauges, 2s polling via `/api/server-stats`).
- **Themes:** Dark (default) & Light mode, toggle in Sidebar and Auth pages.
- **Unread badges:** `pulse` WebSocket channel drives sidebar unread counts.

---

## ⛔ STRICT RULES FOR THE AI AGENT (DO NOT BREAK THESE)
1. **NEVER TEST LOCALLY:** Do NOT run `npm run dev`, `fastapi dev`, or start local dev servers. Do NOT connect to or create local SQLite databases.
2. **BUILD ONLY:** Verify your code by running `npm run build` (Frontend) and `python -m compileall` (Backend).
3. **NO UI REGRESSIONS:** The mobile and desktop UI have gone through extensive debugging. Do NOT rewrite massive UI components from scratch unless explicitly asked. Fix bugs surgically.
4. **DEPLOYMENT:** Once `npm run build` passes, **commit and push to GitHub immediately**. Then, provide me with the exact deployment commands for the server (`./deploy.sh deploy` — NEVER bare `docker compose up`).
5. **RBAC:** Never weaken the exact permission rules in section 4. Backend enforcement always wins over the client.
6. **DIGITS:** All dynamic numbers in the UI must be Latin digits (see section 4 formatting rule).
