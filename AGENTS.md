# PROJECT CONTEXT: ArchSchool

You are working on a production-ready project named **ArchSchool**. Read this entire context carefully before writing any code. 

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

## 4. Authentication & Roles (RBAC)
- **Access Code Only:** There are no passwords. Authentication is done via `username` + a **6-character alphanumeric uppercase Access Code** (e.g., `ROOT01`).
- **Admin:** The `.env` contains `ADMIN_CODE=ROOT01`. The admin can access `/rootvoid` to manage users and assign roles.
- **Roles:** `admin` (full access), `editor` (can edit/delete any assignment), `member` (can only edit/delete own assignments, but can complete/comment on any).

## 5. Deployment Workflow & Scripts
- **GitHub Repo:** `https://github.com/NULLByte-ROOT/archschool` (Branch: `main`).
- **Deployment Script:** `./deploy.sh` on the server — blue-green. `./deploy.sh deploy` pulls, builds the inactive slot, verifies it, switches the host Nginx upstream and soaks; `rollback`, `cleanup`, `status`, `fix-nginx` are the other subcommands. NEVER use `docker compose up -d`/`down`/`--remove-orphans` directly: slots are Compose profiles and the database is shared.
- **Host Nginx WebSocket:** `deploy.sh` checks for `proxy_set_header Upgrade $http_upgrade;` (case-insensitive, anywhere in the site file) and only patches when it is genuinely missing — a hand-written block, with or without comments, is never touched. The injected block sets `proxy_http_version 1.1`, `Upgrade $http_upgrade`, `Connection "upgrade"` and long timeouts; without it the chat fails with "WebSocket is closed before the connection is established". `./deploy.sh fix-nginx` repairs it in place (no rebuild) and restarts Nginx.
- **Traffic switch:** after rewriting `/etc/nginx/conf.d/00-archschool-upstream.conf`, `deploy.sh` runs `systemctl restart nginx` (not reload) so old workers cannot keep serving the previous slot, and verifies the public URL reports the new revision (one retry with an extra restart, then rollback).
- **Database Migrations:** Handled automatically via `Base.metadata.create_all` and custom `_ensure_columns()` logic in `main.py`. Explicit SQL scripts are in `backend/migrations/` (safe to run idempotently).
- **Backup / Restore:** `./deploy.sh backup` writes `archschool_backup_YYYY-MM-DD_HH-MM.tar.gz` in the project root (mode 600: `database.sql`, `uploads.tar.gz`, `.env`, `metadata.txt`). `./deploy.sh restore <archive>` restores on a fresh or existing server (confirmation required) and finishes with a standard deploy. Also `./deploy.sh list-backups`, `deploy --backup`, `--out=DIR`. Archives are git-ignored — never commit them.

## 6. Core Features Implemented
- **Dashboard:** CTA, activity charts, recent chats, upcoming deadlines.
- **Timetable:** Sat-Wed (4 periods, 08:00-14:00), live countdown, next-day preview.
- **Assignments:** Public/shared. Grouped by Urgent/Upcoming/Completed. File attachments (with uploader attribution & delete button). Task-specific comments.
- **Chat:** Telegram-style UI. WebSocket for real-time. Global, Private (DM), and Assignment rooms. Admin can delete any message or clear rooms. Full-screen avatar viewer & Telegram-style profile modal.
- **Themes:** Dark (default) & Light mode, toggle in Sidebar and Auth pages.

---

## ⛔ STRICT RULES FOR THE AI AGENT (DO NOT BREAK THESE)
1. **NEVER TEST LOCALLY:** Do NOT run `npm run dev`, `fastapi dev`, or start local dev servers. Do NOT connect to or create local SQLite databases.
2. **BUILD ONLY:** Verify your code by running `npm run build` (Frontend) and `python -m compileall` (Backend).
3. **NO UI REGRESSIONS:** The mobile and desktop UI have gone through extensive debugging. Do NOT rewrite massive UI components from scratch unless explicitly asked. Fix bugs surgically.
4. **DEPLOYMENT:** Once `npm run build` passes, **commit and push to GitHub immediately**. Then, provide me with the exact deployment commands for the server (`git pull origin main`, `docker compose up -d --build`, or `./deploy.sh`).