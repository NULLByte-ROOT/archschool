# ArchSchool

ArchSchool is a school homework & timetable manager. It tracks assignments,
exams and projects, and shows the weekly class schedule with upcoming work
highlighted per subject.

- **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS v4 + Framer Motion
- **Backend:** FastAPI + SQLAlchemy + Pydantic (SQLite for local dev, PostgreSQL in Docker)

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

## Production

Standard deploy/update:

```bash
git pull origin main
docker compose up -d --build --remove-orphans
docker image prune -f
```

Or use the interactive manager:

```bash
./deploy.sh   # option 5 = update from GitHub (pull + rebuild)
```

The backend expects PostgreSQL; connection settings live in
`backend/.env` and are overridden by `docker-compose.yml`. Existing data is
preserved because schema changes only add columns/tables.

After deploying, users should refresh the app (their role is re-fetched from
`/api/auth/me` automatically).
