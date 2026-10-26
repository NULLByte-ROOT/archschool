from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "ArchSchool API"
    DATABASE_URL: str = "sqlite:///./homework.db"

    # Git SHA of the running build. Injected at image build time so the
    # blue-green deploy script can prove which revision is actually live.
    APP_REVISION: str = "unknown"

    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:6241",
        "http://127.0.0.1:6241",
        "https://archschool.vidxsepehr.ir",
        "http://archschool.vidxsepehr.ir",
    ]

    # Expo starts the web preview on 8081 and a phone in LAN development talks
    # to `http://192.168.x.x:8000`; a regex covers those ephemeral origins
    # without listing every machine. Native iOS/Android requests send no Origin
    # header at all, so CORS only ever gates the optional web build.
    CORS_ORIGIN_REGEX: str = (
        r"^https?://(localhost|127\.0\.0\.1|\[::1\]|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?::\d+)?$"
    )

    SECRET_KEY: str = "change-me-in-production-please"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    ADMIN_CODE: str = "ROOT01"

    # The top-level account. Created automatically on the first boot when both
    # values are present (deploy.sh prompts for them / generates the code).
    OWNER_USERNAME: str = ""
    OWNER_ACCESS_CODE: str = ""

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 25

    # ------------------------------------------------------------------
    #  Anti-cheat / streak configuration
    # ------------------------------------------------------------------
    # A freshly created assignment cannot be marked done before this delay, so
    # the team cannot "complete" work it never had time to do.
    COMPLETION_DELAY_MINUTES: int = 30

    # More than TOGGLE_LIMIT_PER_HOUR toggles of the same assignment inside one
    # hour locks that toggle for TOGGLE_LOCK_MINUTES.
    TOGGLE_LIMIT_PER_HOUR: int = 3
    TOGGLE_LOCK_MINUTES: int = 60

    # The class lives in Iran (UTC+03:30). Streak days/`completed_today` and the
    # 7-day activity buckets are computed against this wall clock instead of the
    # container's UTC clock, so a completion at 01:00 local still belongs to the
    # correct day. Keeping it as a numeric offset avoids relying on the tzdata
    # database, which the slim Docker image does not ship.
    SCHOOL_UTC_OFFSET_HOURS: float = 3.5

    # ------------------------------------------------------------------
    #  Mobile push notifications
    # ------------------------------------------------------------------
    # Master switch for the Expo push transport and the deadline watcher.
    PUSH_NOTIFICATIONS_ENABLED: bool = True

    # How often the in-process watcher looks for assignments entering the
    # 24-hour / 2-hour warning windows. Runs in the uvicorn event loop; no
    # Celery/Redis worker is needed (and blue-green stays single-service).
    DEADLINE_CHECK_INTERVAL_MINUTES: int = 10

    # Only needed when the Expo project turns on "enhanced push security".
    # When set, every request to exp.host carries `Authorization: Bearer …`;
    # when empty the header is omitted (the default public endpoint).
    EXPO_ACCESS_TOKEN: str = ""

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _normalize_origins(cls, origins: list[str]) -> list[str]:
        """Strip whitespace/trailing slashes so an env entry like
        `" https://example.com/"` still matches the browser's Origin header."""
        cleaned: list[str] = []
        for origin in origins:
            value = origin.strip().rstrip("/")
            if value and value not in cleaned:
                cleaned.append(value)
        return cleaned

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()