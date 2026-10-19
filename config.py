import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Set DATABASE_URL in .env (see .env.example).")

DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
if DB_POOL_SIZE < 1 or DB_MAX_OVERFLOW < 0 or DB_POOL_TIMEOUT < 1:
    raise ValueError("Invalid database pool settings.")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
if ACCESS_TOKEN_EXPIRE_MINUTES < 1:
    raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be positive.")


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
