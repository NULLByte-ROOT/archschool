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

    SECRET_KEY: str = "change-me-in-production-please"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    ADMIN_CODE: str = "ROOT01"

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 25

    # Gamification: points granted per assignment attachment, and whether those
    # points are taken back when the uploader deletes their own attachment.
    POINTS_PER_UPLOAD: int = 15
    DEDUCT_POINTS_ON_ATTACHMENT_DELETE: bool = True

    # Points awarded to the specific user who marks a shared assignment done.
    POINTS_PER_ASSIGNMENT: int = 10

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