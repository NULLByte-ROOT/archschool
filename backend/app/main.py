from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from sqlalchemy import inspect, text

from .config import settings
from .database import Base, engine
from .routers import assignments, attachments, auth, messages, uploads, users, ws

Base.metadata.create_all(bind=engine)


def _ensure_columns() -> None:
    """create_all() only creates missing tables, not missing columns.

    This keeps pre-existing production databases in sync with the models while
    still letting new tables (messages, attachments) be created automatically.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    wanted: dict[str, dict[str, str]] = {
        "users": {
            "points": "INTEGER NOT NULL DEFAULT 0",
            "role": "VARCHAR(20) NOT NULL DEFAULT 'member'",
        },
        "assignments": {
            "category": "VARCHAR(20) DEFAULT ''",
            "subtype": "VARCHAR(40) DEFAULT ''",
            "subject_id": "VARCHAR(40) DEFAULT ''",
            "points_awarded": "BOOLEAN NOT NULL DEFAULT FALSE",
            "creator_id": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
        },
        "messages": {
            "reply_to_id": "INTEGER REFERENCES messages(id) ON DELETE SET NULL",
            "is_pinned": "BOOLEAN NOT NULL DEFAULT FALSE",
        },
    }

    for table, columns in wanted.items():
        if table not in tables:
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        missing = {
            name: ddl for name, ddl in columns.items() if name not in existing
        }
        if not missing:
            continue
        with engine.begin() as conn:
            for name, ddl in missing.items():
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def _backfill_rbac_data() -> None:
    """Idempotently migrate pre-existing rows to the new RBAC/public model.

    - grant the ``admin`` role to legacy ``is_admin`` users,
    - point ``creator_id`` at the original ``owner_id``,
    - materialise ``assignment_completions`` for already-completed tasks.
    """
    statements = [
        "UPDATE users SET role = 'admin' WHERE is_admin = TRUE "
        "AND (role IS NULL OR role = 'member')",
        "UPDATE assignments SET creator_id = owner_id WHERE creator_id IS NULL",
        "INSERT INTO assignment_completions (user_id, assignment_id, completed_at) "
        "SELECT a.owner_id, a.id, CURRENT_TIMESTAMP FROM assignments a "
        "WHERE a.completed = TRUE AND a.owner_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM assignment_completions c "
        "WHERE c.assignment_id = a.id AND c.user_id = a.owner_id)",
    ]
    with engine.begin() as conn:
        for statement in statements:
            try:
                conn.execute(text(statement))
            except Exception:  # pragma: no cover - best-effort migration
                pass


_ensure_columns()
_backfill_rbac_data()

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
    ],
    expose_headers=["Content-Disposition"],
    max_age=86400,
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(assignments.router, prefix="/api/assignments", tags=["assignments"])
app.include_router(messages.router, prefix="/api/messages", tags=["messages"])
app.include_router(uploads.router, prefix="/api/uploads", tags=["uploads"])
app.include_router(attachments.router, prefix="/api/attachments", tags=["attachments"])
app.include_router(ws.router, tags=["ws"])


class MediaStaticFiles(StaticFiles):
    """Serve uploads with an explicit inline disposition.

    Uploaded images/PDFs must render directly when their URL is opened in a new
    tab (and inline ``<img>`` previews must not be treated as downloads), so we
    force ``Content-Disposition: inline`` and a sane cache header.
    """

    def file_response(self, *args, **kwargs) -> Response:  # type: ignore[override]
        response = super().file_response(*args, **kwargs)
        content_type = response.headers.get("content-type", "")
        # SVG can carry scripts; never render it inline on our own origin.
        if content_type.startswith("image/svg"):
            response.headers["Content-Disposition"] = "attachment"
        else:
            response.headers.setdefault("Content-Disposition", "inline")
        response.headers.setdefault("Cache-Control", "public, max-age=86400")
        return response


app.mount(
    "/api/media",
    MediaStaticFiles(directory=str(UPLOAD_DIR)),
    name="media",
)


@app.get("/")
def root():
    return {"message": settings.APP_NAME}
