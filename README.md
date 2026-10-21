# ArchSchool

ArchSchool is a school homework & timetable manager. It tracks assignments,
exams and projects, shows the weekly class schedule with a live period
countdown, and includes a team chat with profiles.

- **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS v4 + Framer Motion
- **Backend:** FastAPI + SQLAlchemy + Pydantic (SQLite for local dev, PostgreSQL in Docker)

## Features

- **Dashboard** — activity chart, assignment type breakdown, upcoming
  deadlines, recent chat messages and latest assignment comments.
- **Timetable** — Sat–Wed, four 90-minute periods (08:00–14:00), live
  countdown for the current/next period, and next school day preview.
- **Assignments** — urgent/upcoming/completed groups, filters, per-user
  completion and points.
- **Accounts** — username + 6-character access code registration and login
  (uppercase English letters and numbers only; the admin code still works),
  editable bio and avatar.
- **Chat** — global, private and per-assignment rooms; profile modal, pin,
  reply, forward, attachments, admin delete-any/clear-room.
- **Themes** — dark monochrome (default) and a soft light theme, toggle in
  Settings.


## Structure

```
backend/   FastAPI app (app/models.py, app/schemas.py, app/routers/)
frontend/  React app (src/components, src/pages, src/lib)
```

## Local development

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate      # Windows
pip install -r requirements.txt   # or use uv with pyproject.toml
uvicorn app.main:app --reload --port 8000
```

Copy `backend/.env.example` to `backend/.env` and adjust values as needed.
New users can register from `/register` with a username and a 6-character
access code; usernames are case-insensitive on lookup and start with a capital
letter. Access codes accept only uppercase English letters and numbers.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The API base URL is read from `VITE_API_URL` (see `frontend/.env.example`),
defaulting to `http://localhost:8000/api`.

## Roles & public assignments

Assignments are shared across the team. Every user can see every assignment.

- `admin` — manages users and all assignments
- `editor` — can edit/delete any assignment
- `member` — can edit/delete only assignments they created

Completion is per user (`assignment_completions` table). Marking a task done
awards points to that specific user.

## Database migrations

The backend applies the schema changes automatically on startup
(`Base.metadata.create_all` + `app/main.py::_ensure_columns` and
`_backfill_rbac_data`), so a normal deploy needs no manual SQL.

For an explicit, idempotent migration (safe to run repeatedly, never drops
data), use [`backend/migrations/001_rbac_public_assignments.sql`](backend/migrations/001_rbac_public_assignments.sql):

```bash
# PostgreSQL inside the compose stack
docker compose exec -T db psql -U postgres -d archschool_db \
  < backend/migrations/001_rbac_public_assignments.sql
```

It adds `users.role`, `assignments.creator_id` and `assignment_completions`,
then backfills existing admins, creators and completed assignments.

For username/password auth and profiles, apply
[`backend/migrations/002_user_passwords_profiles.sql`](backend/migrations/002_user_passwords_profiles.sql)
the same way:

```bash
docker compose exec -T db psql -U postgres -d archschool_db \
  < backend/migrations/002_user_passwords_profiles.sql
```

It adds `users.password`, `users.avatar_url`, `users.bio` and
`users.last_seen`. Both migrations are idempotent and only add columns.

## Production (blue-green)

Two identical slots (`blue` and `green`) run the same images on different
internal ports. A deploy always builds and starts the **inactive** slot, waits
until it is healthy, verifies it end-to-end, and only then flips the host
Nginx upstream. The previous slot keeps running through a soak window so a bad
release can be reverted by flipping traffic back.

```
Internet -> Host Nginx -> upstream archschool_app -> 127.0.0.1:6241 (blue)
                                                  -> 127.0.0.1:6242 (green)
```

- `archschool_db` and the `archschool_uploads` volume are **shared** by both
  slots — the database is never duplicated.
- Slots are Compose profiles, so a bare `docker compose up -d` only starts the
  database. Always use `./deploy.sh`.
- Frontend ports are published on `127.0.0.1` only; the only public entry point
  is host Nginx.

### Commands

```bash
sudo ./deploy.sh deploy      # pull + build inactive slot + verify + switch + soak
sudo ./deploy.sh rollback    # move traffic back to the previous slot
sudo ./deploy.sh status      # slots, health, image revisions, active target
sudo ./deploy.sh cleanup     # delete the inactive slot's containers + images
sudo ./deploy.sh             # interactive menu
```

Useful flags: `--skip-pull`, `--soak=30`, `--no-soak`, `--keep-old`, `--yes`,
`--timeout=180`.

### What a deploy actually does

1. `git pull` and stamp `GIT_SHA` into the images.
2. Build the inactive slot's images (`archschool-*:<sha>`). Nothing running is
   touched, so a build failure cannot cause downtime.
3. Start it, then wait for both containers to report `healthy`
   (backend `/api/health` checks the database).
4. Smoke-test it: static frontend, `/version` == the new SHA, `/api/health`
   through the frontend, and a WebSocket handshake against `/api/ws`.
5. Rewrite `/etc/nginx/conf.d/00-archschool-upstream.conf`, run `nginx -t`,
   then `systemctl reload nginx` (graceful — in-flight requests complete).
6. Verify the public URL reports the new revision. On failure: automatic
   rollback.
7. Soak for 60s with continuous health probes. On failure: automatic rollback.
8. Stop (but keep) the previous slot and its images for rollback, then prune
   only dangling images.

### One-time host Nginx change

`deploy.sh` performs this automatically (timestamped backup, `nginx -t`, and an
automatic revert if validation fails). The change is:

```diff
- proxy_pass http://127.0.0.1:6241;
+ proxy_pass http://archschool_app;
```

plus the managed upstream file:

```nginx
# /etc/nginx/conf.d/00-archschool-upstream.conf
upstream archschool_app {
    server 127.0.0.1:6242;
}
```

If the script cannot find the expected line it prints the diff and exits
without touching anything. Override detection with
`NGINX_SITE_CONF=/etc/nginx/sites-available/archschool`.

Keep `client_max_body_size 30m;` and the `Upgrade`/`Connection "upgrade"`
headers in the site block — uploads and the chat socket depend on them.

### Database rules for blue-green

Both slots share one PostgreSQL, and the previous slot serves traffic for a
short time (and may be restarted for a rollback). Therefore:

- **Additive changes only per release** (add columns/tables, new nullable
  fields). Destructive changes must ship one release later.
- Startup migrations run under a Postgres advisory lock, so two instances can
  never execute DDL at the same time.

### Notes and limits

- After the switch, sockets connected to the previous slot stop receiving new
  chat broadcasts until it is stopped (60s later); clients then reconnect
  automatically within ~1s.
- A browser holding the previous `index.html` may 404 on a lazily loaded chunk
  after a switch; a refresh fixes it. Deploy at low-traffic times.
- Direct access to `http://SERVER_IP:6241` no longer works — slots bind to
  loopback. Use the domain (or `docker port`).
- Container picks are driven by Compose labels and the upstream file, so
  `.deploy-state` can be deleted without breaking anything.

The backend expects PostgreSQL; connection settings live in `backend/.env` and
are overridden by `docker-compose.yml`. Existing data is preserved because
schema changes only add columns/tables.

After deploying, users should refresh the app (their role is re-fetched from
`/api/auth/me` automatically).
