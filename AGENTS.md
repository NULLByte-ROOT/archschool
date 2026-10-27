# PROJECT CONTEXT: ArchSchool — SINGLE SOURCE OF TRUTH

You are working on a production-ready project named **ArchSchool**. This file is the single source of truth for all future AI sessions. Read this entire context carefully before writing any code.

## 1. Project Overview
ArchSchool is a social-network-style school workspace for a class team (11th grade). It manages assignments, timetables, chats, and gamification (streaks + percentage-based leaderboard). The UI is strictly RTL (Persian) and uses a dark/light theme system.

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
  - **Friend:** CAN chat (global, DM, assignment comments). CAN view and comment on assignments. Cannot create/edit assignments. CAN edit and delete **their own** chat messages (for everyone) but cannot delete anyone else's.
  - **Admin:** Has all Friend capabilities + CAN create/edit/delete assignments + CAN delete ANY chat message and clear rooms. Nobody can edit someone else's message.
  - **Owner (special account):** Has all Admin capabilities + CAN view server stats (`/api/server-stats`, psutil polling on the `ServerStatsPage`) + CAN change the access code of any user (`PATCH /api/users/{user_id}/code` — Owner-only endpoint).
- **Owner account:** Bootstrapped from `backend/.env` keys `OWNER_USERNAME` / `OWNER_ACCESS_CODE` by `_ensure_owner_account()` in `main.py`, which **re-applies the env code at every boot** — the `.env` is the source of truth for the Owner's OWN code. The Owner's own code therefore must be changed via the server (menu option `14) Set Owner Credentials`), and `PATCH /api/users/{id}/code` returns «کد حساب Owner از backend/.env کنترل می‌شود؛ از منوی سرور تغییر دهید» if the Owner tries to change their own code while an env code is set. Codes for all OTHER users are changed only through the Owner-only endpoint / the Users page "Change Code" button (visible to Owner only).
- **Role management:** Done on the `/rootvoid` Users page by admin/owner. Only an Owner can mint another Owner.
- **Chat implementation notes:** `is_staff` = admin/owner (assignment CRUD, delete-any, room clearing). Every sender can edit and delete **their own** message for everyone (`PATCH/DELETE /api/messages/{id}`); staff can additionally delete any message. Comments on an assignment live in the embedded `ChatRoom room=assignment:<id>` on the assignment detail page, where members are allowed to write; the `/chat` page itself remains blocked for members.
- **Number formatting rule:** ALL dynamic numbers in the UI use Latin (English) digits. Persian calendar dates use locale `"fa-IR-u-nu-latn"` (Persian wording/months, Latin digits); pure numbers/bytes/counters use `"en-US"` `Intl.NumberFormat`. Never use bare `"fa-IR"` locales or Persian digit converters in new code.

### 4.1 Role-gated UI matrix (single source of truth for web + mobile)
Every gated element below is enforced on the backend too; the UI must never show a control the API will reject, and must never hide a control the role is allowed to use.

| Element | Minimum role | Web | Mobile |
| --- | --- | --- | --- |
| Assignments, Leaderboard, Profile, Timetable, Team Status | `member` (everyone) | always in sidebar | always in tab bar |
| Chat tab / DM / global chat | `friend` | chat nav hidden for members | chat tab locked for members |
| Assignment comments (inside the assignment room) | `member` | allowed | allowed |
| «کاربران» page / user management | `admin` | `/rootvoid` (`adminOnly`) | `/users` row in Profile `// APP` |
| «افزودن تکلیف» button | `admin` | `AssignmentsPage` header + empty state (`isAdmin`) | create FAB / empty state (`isStaff`) |
| «پاک کردن کل گفتگو» + delete any message | `admin` | chat room staff menu | chat room staff menu |
| Edit/delete own chat message | `friend` | always (own only) | always (own only) |
| «تنظیمات زنگ‌های مدرسه» | `owner` | `/admin/bells` (`ownerOnly`) + Sidebar `// OWNER` | `/admin-bells` + Profile `// OWNER` row |
| «آمار سرور» | `owner` | `/admin/stats` (`ownerOnly`) + Sidebar `// OWNER` | (web only) |
| «تغییر کد دسترسی» | `owner` | Users page code sheet (`isOwner`) | Users page code sheet (`isOwner`) |
| Owner hint / owner badge | `owner` | profile role badge | Profile `// OWNER` hint |

Notes:
- `isAdmin` on the web includes `owner` (`user.is_admin || role === "admin" || role === "owner"`), so the Owner sees the `// ADMIN` block **and** the `// OWNER` block.
- `isStaff` on mobile is the same predicate as web `isAdmin`; `isOwner` is `role === "owner"` only.
- Never gate a control with `!isMember` when the intended minimum is `admin` — that leaks the control to `friend`.


## 5. Deployment Workflow & Scripts
- **GitHub Repo:** `https://github.com/NULLByte-ROOT/archschool` (Branch: `main`).
- **Deployment Script:** `./deploy.sh` on the server — blue-green. `./deploy.sh deploy` pulls, builds the inactive slot, verifies it, switches the host Nginx upstream and soaks; `rollback`, `cleanup`, `status`, `fix-nginx` are the other subcommands. NEVER use `docker compose up -d`/`down`/`--remove-orphans` directly: slots are Compose profiles and the database is shared.
- **Interactive menu:** Running `./deploy.sh` with no args opens the menu; option **`14) Set Owner Credentials (Username & Access Code)`** prompts for a username and a 6-char uppercase access code, writes `OWNER_USERNAME`/`OWNER_ACCESS_CODE` into `backend/.env`, then offers to restart the backend to apply.
- **Host Nginx WebSocket:** `deploy.sh` detects the headers by content, per location — never by a marker comment, so a hand-written block is never touched. It only inserts the block into a proxying location that lacks the headers; `location /` upgrading does not help when a more specific `location ^~ /api/` also proxies, because `/api/ws` takes that branch, arrives at FastAPI as a plain GET and answers 404. The injected block sets `proxy_http_version 1.1`, `Upgrade $http_upgrade`, `Connection "upgrade"` and long timeouts. `./deploy.sh fix-nginx` repairs it in place (no rebuild) and restarts Nginx. The public WS probe uses `curl --http1.1` and accepts `101/400/401/403/426` — upgrades do not exist in HTTP/2, so without `--http1.1` the probe gets a false 404.
- **WebSocket handshake:** `backend/app/routers/ws.py` accepts the socket *first* and then closes with `1008` for a bad token/room. A close before `accept()` becomes a failed HTTP handshake, which browsers can only report as `1006` with no reason; `logging.basicConfig` is configured in `main.py` so the `ws handshake room=… token=present|MISSING host=…` line is actually printed.
- **Traffic switch:** after rewriting `/etc/nginx/conf.d/00-archschool-upstream.conf`, `deploy.sh` runs `systemctl restart nginx` (not reload) so old workers cannot keep serving the previous slot, and verifies the public URL reports the new revision (one retry with an extra restart, then rollback).
- **Database Migrations:** Handled automatically via `Base.metadata.create_all` and custom `_ensure_columns()` logic in `main.py`. Explicit SQL scripts are in `backend/migrations/` (safe to run idempotently). `003_stats_streaks_remove_points.sql` is the exception to the automatic path: it **drops columns**, so it must be run only after `./deploy.sh deploy` finished and the old slot is stopped (a still-running pre-003 slot selects `points` and would break).
- **Backup / Restore:** `./deploy.sh backup` writes `archschool_backup_YYYY-MM-DD_HH-MM.tar.gz` in the project root (mode 600: `database.sql`, `uploads.tar.gz`, `.env`, `metadata.txt`). `./deploy.sh restore <archive>` restores on a fresh or existing server (confirmation required) and finishes with a standard deploy. Also `./deploy.sh list-backups`, `deploy --backup`, `--out=DIR`. Archives are git-ignored — never commit them.

## 6. Core Features Implemented
- **Dashboard:** Hero streak widget (current/best/team-record streak, pulsing red “at risk” warning when nothing is completed today), percentage top-3, personal focus, class activity pulse, 7-day class trend and tomorrow's schedule — every widget links to its page.
- **Leaderboard & Stats:** Ranked strictly by `completion_percentage`; ties go to the earlier `last_completion_time`. Endpoints: `GET /api/stats/leaderboard`, `GET /api/stats/overview` (dashboard) and `GET /api/stats/users/{id}` (profile modal). Streaks (`current_streak`, `best_streak`, team record) and 7-day activity are computed on demand from `assignment_completions` using the school clock (`SCHOOL_UTC_OFFSET_HOURS=3.5`), never from cached columns.
- **Anti-cheat:** A new assignment cannot be marked done for `COMPLETION_DELAY_MINUTES` (30) after creation; more than `TOGGLE_LIMIT_PER_HOUR` (3) toggles of the same assignment inside one hour locks that toggle for `TOGGLE_LOCK_MINUTES` (60), tracked in `completion_toggle_guards` and returned as HTTP 429. The points system is fully retired; `backend/migrations/003_stats_streaks_remove_points.sql` drops the legacy `users.points` / `assignments.points_awarded` columns after a successful deploy.
- **Timetable:** Sat-Wed. Bell times come live from `GET /api/schedule`; the countdown/status box detects gaps between bells as «زنگ تفریح» and counts down to the next bell. `/admin/bells` saves through `PUT /api/schedule` and immediately refreshes the shared bell cache. Next-day preview included.
- **Assignments:** Public/shared. Grouped by Urgent/Upcoming/Completed. File attachments (with uploader attribution & delete button). Task-specific comment rooms on the detail page.
- **Chat:** Telegram-style UI. WebSocket for real-time. Global, Private (DM), and Assignment rooms. Senders can edit/delete their own messages; staff (admin/owner) can delete any message or clear rooms. Full-screen avatar viewer & Telegram-style profile modal; swipe-to-reply.
- **Server Stats:** Owner-only page (CPU/RAM/net gauges, 2s polling via `/api/server-stats`).
- **Themes:** Dark (default) & Light mode, toggle in Sidebar and Auth pages.
- **Unread badges:** `pulse` WebSocket channel drives sidebar unread counts.

## 7. Mobile App & Push Notifications
- **Repository:** The Expo client is a separate repo at `D:\Site\archschool-mobile` (GitHub `NULLByte-ROOT/archschool-mobile`), not part of the Vite build. It uses Expo SDK 58 / RN 0.88 / Expo Router, React Query, Zustand, SecureStore, Reanimated, expo-notifications and expo-updates. Its `AGENTS.md` is the source of truth for mobile-only rules.
- **API/WS:** Production base `https://archschool.vidxsepehr.ir/api`, WS `wss://archschool.vidxsepehr.ir/api/ws?room=…&token=…`. `EXPO_PUBLIC_API_URL` overrides the base for development builds only. The socket is receive-only; all writes go through REST.
- **Push models:** `push_tokens` (`id`, `user_id`, `token` unique, `device_type`, `created_at`, `updated_at`) and `deadline_notifications` (`assignment_id`, `threshold_hours`, unique together, `sent_at`). The deadline marker is global per assignment/threshold because one send fans out to every still-pending user. Both tables are created by the additive boot migration — no manual SQL.
- **Endpoints:** `POST /api/users/push-token` (`{token, device_type}`; validates `ExponentPushToken[...]` / `ExpoPushToken[...]`, re-owns a token already registered to another account) and `DELETE /api/users/push-token` (`{token}`). Logout unregisters silently.
- **Triggers (`backend/app/notifications.py`):** chat messages reach the same audience as the room (global: admin/friend/owner, never chat-locked members; DM: receiver only; assignment comments: everyone active except the author); new assignments reach every active account except the creator; deadline reminders fire 24h and 2h before `due_date` only to users who have not completed the task.
- **Delivery (`backend/app/push.py`):** Expo HTTP API via `httpx`, batches of 100, background task/thread so requests never block, `DeviceNotRegistered` tokens pruned. Failures are logged as `archschool.push`, never raised.
- **Scheduler:** One asyncio loop in the FastAPI lifespan (10-minute interval, 20s boot delay). Thresholds already crossed when an assignment is created are reserved immediately, and the unique row is committed before sending, so blue-green/restarts cannot double-send.
- **Env:** `PUSH_NOTIFICATIONS_ENABLED` (default true), `DEADLINE_CHECK_INTERVAL_MINUTES` (10), `CORS_ORIGIN_REGEX` in `backend/.env.example`. The Expo endpoint is the hardcoded official `https://exp.host/--/api/v2/push/send`. Native mobile requests send no `Origin`; the regex only exists for Expo web/LAN previews.
- **Deep links:** Notification `data` contains `type` (`chat`/`assignment`/`deadline`), `room` (`global`, `dm:<low>:<high>`, `assignment:<id>`) and `assignment_id`; the app opens the room/detail on tap, cold start included.
- **EAS/OTA:** `eas.json` has development (dev client, APK), preview (APK) and production (AAB, autoIncrement) profiles with matching update channels. `eas init` fills `extra.eas.projectId`; `eas update:configure` replaces the placeholder `updates.url`. OTA is `ON_LOAD` with `runtimeVersion.policy: appVersion`.
- **Validation:** `npm run typecheck` and `npx expo export --platform android --output-dir .expo-export-test` in `archschool-mobile`; `py -m compileall -q backend\app` here. Never start Metro/FastAPI locally.

---

## ⛔ STRICT RULES FOR THE AI AGENT (DO NOT BREAK THESE)
1. **NEVER TEST LOCALLY:** Do NOT run `npm run dev`, `fastapi dev`, or start local dev servers. Do NOT connect to or create local SQLite databases.
2. **BUILD ONLY:** Verify your code by running `npm run build` (Frontend) and `python -m compileall` (Backend). For the mobile app, run `npm run typecheck` and `npx expo export --platform android --output-dir .expo-export-test`.
3. **NO UI REGRESSIONS:** The mobile and desktop UI have gone through extensive debugging. Do NOT rewrite massive UI components from scratch unless explicitly asked. Fix bugs surgically.
4. **DEPLOYMENT:** Once `npm run build` passes, **commit and push to GitHub immediately**. Then, provide me with the exact deployment commands for the server (`./deploy.sh deploy` — NEVER bare `docker compose up`).
5. **RBAC:** Never weaken the exact permission rules in section 4. Backend enforcement always wins over the client.
6. **DIGITS:** All dynamic numbers in the UI must be Latin digits (see section 4 formatting rule).
7. **MOBILE REPO:** The Expo client lives in `D:\Site\archschool-mobile` with its own git history. Commit/push it separately; never copy it into this repo or add it as a submodule.
