import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlalchemy import URL

load_dotenv(Path(__file__).resolve().parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
# Containers use separate fields so passwords containing @, / or % work too.
if os.getenv("DATABASE_HOST"):
    DATABASE_URL = URL.create(
        "postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["DATABASE_HOST"],
        port=int(os.getenv("DATABASE_PORT", "5432")),
        database=os.environ["POSTGRES_DB"],
    ).render_as_string(hide_password=False)
if not DATABASE_URL:
    raise RuntimeError("Set DATABASE_URL in .env (see .env.example).")

DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
if DB_POOL_SIZE < 1 or DB_MAX_OVERFLOW < 0 or DB_POOL_TIMEOUT < 1:
    raise ValueError("Invalid database pool settings.")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
JWT_IAT_LEEWAY_SECONDS = int(os.getenv("JWT_IAT_LEEWAY_SECONDS", "5"))
if not 0 <= JWT_IAT_LEEWAY_SECONDS <= 30:
    raise ValueError("JWT_IAT_LEEWAY_SECONDS must be between 0 and 30.")
if ACCESS_TOKEN_EXPIRE_MINUTES < 1:
    raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be positive.")

CORS_ORIGINS = [origin.strip() for origin in os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
).split(",") if origin.strip()]
if "*" in CORS_ORIGINS:
    raise ValueError("CORS_ORIGINS must list explicit frontend origins, not *.")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
if LOG_LEVEL not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
    raise ValueError("Invalid LOG_LEVEL.")


def env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    if value not in {"true", "false", "1", "0"}:
        raise ValueError(f"{name} must be true/false or 1/0.")
    return value in {"true", "1"}


EMAIL_ENABLED = env_bool("EMAIL_ENABLED")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "notifications@taskhub.local")
SMTP_USE_TLS = env_bool("SMTP_USE_TLS", "true")
SMTP_USE_SSL = env_bool("SMTP_USE_SSL")
SMTP_TIMEOUT_SECONDS = float(os.getenv("SMTP_TIMEOUT_SECONDS", "5"))
if EMAIL_ENABLED:
    if not SMTP_HOST or not SMTP_FROM or "\n" in SMTP_FROM or "\r" in SMTP_FROM:
        raise ValueError("Email requires SMTP_HOST and a valid SMTP_FROM.")
    if SMTP_USE_TLS and SMTP_USE_SSL:
        raise ValueError("Use either SMTP_USE_TLS (STARTTLS) or SMTP_USE_SSL, not both.")
    if not 1 <= SMTP_PORT <= 65535 or SMTP_TIMEOUT_SECONDS <= 0:
        raise ValueError("Invalid SMTP port or timeout.")
    if bool(SMTP_USERNAME) != bool(SMTP_PASSWORD):
        raise ValueError("Set both SMTP_USERNAME and SMTP_PASSWORD, or neither.")

REDIS_URL = os.getenv("REDIS_URL", "")
TAGS_CACHE_TTL_SECONDS = int(os.getenv("TAGS_CACHE_TTL_SECONDS", "60"))
TAGS_CACHE_PREFIX = os.getenv("TAGS_CACHE_PREFIX", "taskhub:tags:v1")
if TAGS_CACHE_TTL_SECONDS < 1 or not TAGS_CACHE_PREFIX:
    raise ValueError("Tag cache requires a positive TTL and a nonempty prefix.")

# Separate Redis databases keep queue/results independent of the optional cache.
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
CELERY_TIMEZONE = os.getenv("CELERY_TIMEZONE", "Asia/Ho_Chi_Minh")

ZoneInfo(CELERY_TIMEZONE)  # Fail at startup for an invalid schedule timezone.
