from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

database_url = settings.DATABASE_URL
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)

# ۱. موتور اتصال
engine = create_engine(
    database_url,
    # این فقط برای SQLite لازمه، چون SQLite تو thread های مختلف
    # به‌صورت پیش‌فرض مشکل داره
    connect_args={"check_same_thread": False}
    if database_url.startswith("sqlite")
    else {},
)


SessionLocal = sessionmaker(
    autocommit=False,  
    autoflush=False,   
    bind=engine,
)


Base = declarative_base()


def get_db():

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()