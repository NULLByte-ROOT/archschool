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

## Production

```bash
docker compose up -d --build
```

The backend expects PostgreSQL; connection settings live in
`backend/.env` and are overridden by `docker-compose.yml`.
