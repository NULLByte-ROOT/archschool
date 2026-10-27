import asyncio
import logging
import os
from contextlib import asynccontextmanager, contextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from sqlalchemy import func, inspect, text

from . import models
from .analytics import school_date
from .config import settings
from .database import Base, engine
from .routers import (
    assignments,
    attachments,
    auth,
    messages,
    schedule,
    server_stats,
    stats,
    uploads,
    users,
    ws,
)
from .security import is_valid_access_code, normalize_access_code

logger = logging.getLogger("archschool.boot")

# uvicorn only configures its own "uvicorn.*" loggers and leaves the root logger
# at WARNING with no handler, so every `logger.info(...)` from app code would be
# silently dropped. The WebSocket handshake log is the primary diagnostic for
# "the browser shows 1006 and nobody knows why", so make sure it is printed.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(levelname)s:     %(name)s - %(message)s",
)

# Arbitrary but stable Postgres advisory-lock key ("ARCH"). Blue-green runs two
# backend instances against one database; the lock makes sure only one of them
# can execute DDL at a time.
MIGRATION_LOCK_KEY = 0x41524348


@contextmanager
def _migration_lock():
    """Serialize boot migrations across concurrently starting instances.

    A session-level advisory lock is released explicitly (and automatically by
    Postgres if the process dies), so a crashed boot can never wedge future
    deploys. Non-Postgres backends (local SQLite) skip the lock entirely.
    """
    if engine.dialect.name != "postgresql":
        yield
        return

    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
        conn.commit()
        try:
            yield
        finally:
            try:
                conn.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": MIGRATION_LOCK_KEY},
                )
                conn.commit()
            except Exception:  # pragma: no cover - connection already gone
                logger.warning("Could not release the migration advisory lock")


def _ensure_columns() -> None:
    """create_all() only creates missing tables, not missing columns.

    This keeps pre-existing production databases in sync with the models while
    still letting new tables (messages, attachments) be created automatically.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    wanted: dict[str, dict[str, str]] = {
        "users": {
            "role": "VARCHAR(20) NOT NULL DEFAULT 'member'",
            "password": "VARCHAR(255)",
            "avatar_url": "VARCHAR(500)",
            "bio": "TEXT NOT NULL DEFAULT ''",
            "last_seen": "TIMESTAMP",
        },
        "assignments": {
            "category": "VARCHAR(20) DEFAULT ''",
            "subtype": "VARCHAR(40) DEFAULT ''",
            "subject_id": "VARCHAR(40) DEFAULT ''",
            "creator_id": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
        },
        "messages": {
            "reply_to_id": "INTEGER REFERENCES messages(id) ON DELETE SET NULL",
            "is_pinned": "BOOLEAN NOT NULL DEFAULT FALSE",
            "edited_at": "TIMESTAMP",
        },
        "push_tokens": {
            "notify_chat": "BOOLEAN NOT NULL DEFAULT TRUE",
            "notify_assignments": "BOOLEAN NOT NULL DEFAULT TRUE",
            "notify_deadlines": "BOOLEAN NOT NULL DEFAULT TRUE",
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
            # Never let a deploy block live traffic behind a DDL lock for long;
            # failing fast leaves the currently active slot serving.
            try:
                conn.execute(text("SET LOCAL lock_timeout = '10s'"))
            except Exception:  # pragma: no cover - backend without the setting
                pass
            for name, ddl in missing.items():
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def _backfill_rbac_data() -> None:
    """Idempotently migrate pre-existing rows to the new RBAC/public model.

    - grant the ``admin`` role to legacy ``is_admin`` users,
    - convert retired ``editor`` users to ``admin`` (the role no longer exists),
    - point ``creator_id`` at the original ``owner_id``,
    - materialise ``assignment_completions`` for already-completed tasks.
    """
    statements = [
        "UPDATE users SET role = 'admin' WHERE is_admin = TRUE "
        "AND (role IS NULL OR role = 'member')",
        "UPDATE users SET role = 'admin' WHERE role = 'editor'",
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


def _backfill_daily_activity() -> None:
    """Seed the delete-safe activity ledger from the completions that exist now.

    Runs once (the table is empty on the first boot after this feature lands).
    Afterwards the ledger is maintained by the toggle endpoint and is never
    rewritten, which is exactly what keeps streaks alive when an assignment is
    deleted.
    """
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        if db.query(models.DailyActivity).first() is not None:
            return
        counts: dict[tuple[int, object], int] = {}
        for completion in db.query(models.AssignmentCompletion).all():
            if not completion.completed_at:
                continue
            key = (completion.user_id, school_date(completion.completed_at))
            counts[key] = counts.get(key, 0) + 1
        for (user_id, day), count in counts.items():
            db.add(
                models.DailyActivity(
                    user_id=user_id,
                    activity_date=day,
                    completions=count,
                )
            )
        db.commit()


def _run_boot_migrations() -> None:
    with _migration_lock():
        Base.metadata.create_all(bind=engine)
        _ensure_columns()
        _backfill_rbac_data()
        _backfill_daily_activity()
        _seed_school_schedule()
        _ensure_owner_account()


def _ensure_owner_account() -> None:
    """Create/refresh the ``owner`` account defined by the backend .env.

    Runs on every boot so a code rotation picked up by a new deploy lands in
    the database automatically. Missing or invalid env values are skipped
    with a single warning instead of blocking the deploy. Idempotent: the
    account is only touched when something actually changed.
    """
    username = (settings.OWNER_USERNAME or "").strip()
    try:
        code = normalize_access_code(settings.OWNER_ACCESS_CODE or "")
    except Exception:  # pragma: no cover - normalize never raises today
        code = ""
    if not username or not is_valid_access_code(code):
        if username or settings.OWNER_ACCESS_CODE:
            logger.warning(
                "OWNER_USERNAME/OWNER_ACCESS_CODE incomplete; owner account not "
                "created (code must be exactly 6 alphanumeric uppercase chars)"
            )
        return

    from .database import SessionLocal
    from datetime import datetime, UTC

    with SessionLocal() as db:
        user = (
            db.query(models.User)
            .filter(func.lower(models.User.username) == username.lower())
            .first()
        )
        try:
            if user is None:
                # The access code is unique in the users table: if some other
                # account already holds it, refuse loudly instead of crashing
                # the boot with an integrity error.
                taken = (
                    db.query(models.User)
                    .filter(func.upper(models.User.code) == code)
                    .first()
                )
                if taken:
                    logger.warning(
                        "owner code already used by another account (%s); "
                        "owner account not created",
                        taken.username,
                    )
                    return
                db.add(
                    models.User(
                        username=username,
                        code=code,
                        is_admin=True,
                        role=models.ROLE_OWNER,
                        is_active=True,
                        last_seen=datetime.now(UTC).replace(tzinfo=None),
                    )
                )
                db.commit()
                logger.info("Owner account created (user=%s)", username)
            elif not models.is_owner(user):
                user.is_admin = True
                user.role = models.ROLE_OWNER
                db.commit()
                logger.info("Existing user promoted to owner (user=%s)", username)
            elif user.code.upper() != code:
                user.code = code
                user.is_active = True
                db.commit()
                logger.info("Owner access code updated from environment")
            elif not user.is_active:
                user.is_active = True
                db.commit()
        except Exception:  # pragma: no cover -never block the deploy slot
            db.rollback()
            logger.exception("Owner account bootstrap failed; continuing boot")


def _seed_school_schedule() -> None:
    """Insert the default 08:00-14:00 day once, on a fresh database.

    Idempotent: existing rows (admin-configured bell times) are never touched;
    this only fills the table the first time it is created.
    """
    if engine.dialect.name != "postgresql":
        return  # local/dev engines are handled by the router fallback

    from .database import SessionLocal

    with SessionLocal() as db:
        if db.query(models.SchoolSchedule).count() > 0:
            return
        for number, (start, end) in enumerate(
            [
                ("08:00", "09:30"),
                ("09:30", "11:00"),
                ("11:00", "12:30"),
                ("12:30", "14:00"),
            ],
            start=1,
        ):
            db.add(
                models.SchoolSchedule(
                    period_number=number, start_time=start, end_time=end
                )
            )
        db.commit()
        logger.info("Seeded default school schedule (08:00-14:00, 4 periods)")


_run_boot_migrations()

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Own the deadline watcher for the lifetime of the process.

    The task is created after boot migrations and cancelled on shutdown; its
    first pass waits 20 seconds so a blue-green slot is healthy before it can
    touch Expo. ``asyncio.to_thread`` keeps the DB scan off the event loop.
    """
    watcher: asyncio.Task[None] | None = None
    if settings.PUSH_NOTIFICATIONS_ENABLED:
        from .notifications import deadline_watcher

        watcher = asyncio.create_task(
            deadline_watcher(settings.DEADLINE_CHECK_INTERVAL_MINUTES),
            name="archschool-deadline-watcher",
        )
    try:
        yield
    finally:
        if watcher is not None:
            watcher.cancel()
            with suppress(asyncio.CancelledError):
                await watcher


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
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
app.include_router(schedule.router, prefix="/api/schedule", tags=["schedule"])
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(server_stats.router, prefix="/api/server-stats", tags=["server-stats"])
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


@app.get("/api/health", include_in_schema=False)
def health(response: Response):
    """Readiness probe used by Docker healthchecks and the deploy script.

    Returns 503 when the database is unreachable so a broken build can never be
    promoted by the blue-green switch. The revision is the git SHA baked into
    the image, which lets ``deploy.sh`` prove that the new build is live.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check failed: database is unreachable")
        response.status_code = 503
        return {"status": "degraded", "revision": settings.APP_REVISION}

    return {"status": "ok", "revision": settings.APP_REVISION}


@app.get("/")
def root():
    return {"message": settings.APP_NAME}
