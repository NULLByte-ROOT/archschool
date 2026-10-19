from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from .config import settings
from .database import Base, engine
from .routers import assignments, auth, users

Base.metadata.create_all(bind=engine)


def _ensure_assignment_columns() -> None:
    """create_all() only creates missing tables, not missing columns, so add
    the newer assignment fields to pre-existing SQLite databases."""
    inspector = inspect(engine)
    if "assignments" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("assignments")}
    wanted = {
        "category": "VARCHAR(20) DEFAULT ''",
        "subtype": "VARCHAR(40) DEFAULT ''",
        "subject_id": "VARCHAR(40) DEFAULT ''",
    }
    missing = {name: ddl for name, ddl in wanted.items() if name not in existing}
    if not missing:
        return
    with engine.begin() as conn:
        for name, ddl in missing.items():
            conn.execute(text(f"ALTER TABLE assignments ADD COLUMN {name} {ddl}"))


_ensure_assignment_columns()

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


@app.get("/")
def root():
    return {"message": settings.APP_NAME}