from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Homework Manager API"
    DATABASE_URL: str = "sqlite:///./homework.db"

    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://0.0.0.0:5173",
        " http://10.32.179.31:5173"
    ]

    SECRET_KEY: str = "change-me-in-production-please"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    ADMIN_CODE: str = "ROOT01"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()