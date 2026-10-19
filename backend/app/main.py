from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from .config import settings
from .database import Base, engine
from .routers import assignments, auth, messages, uploads, users, ws

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
        },
        "assignments": {
            "category": "VARCHAR(20) DEFAULT ''",
            "subtype": "VARCHAR(40) DEFAULT ''",
            "subject_id": "VARCHAR(40) DEFAULT ''",
            "points_awarded": "BOOLEAN NOT NULL DEFAULT FALSE",
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


_ensure_columns()

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(assignments.router, prefix="/api/assignments", tags=["assignments"])
app.include_router(messages.router, prefix="/api/messages", tags=["messages"])
app.include_router(uploads.router, prefix="/api/uploads", tags=["uploads"])
app.include_router(ws.router, tags=["ws"])

app.mount("/api/media", StaticFiles(directory=str(UPLOAD_DIR)), name="media")


@app.get("/")
def root():
    return {"message": settings.APP_NAME}
