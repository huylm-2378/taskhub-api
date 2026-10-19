from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt

from config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_SECRET_KEY

if len(JWT_SECRET_KEY.encode("utf-8")) < 32:
    raise RuntimeError("Set JWT_SECRET_KEY to a random secret of at least 32 bytes in .env.")

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


# Check an actual hash even for an unknown user or a legacy profile.
_DUMMY_HASH = hash_password("dummy-password-for-login-timing")


def verify_password(password: str, hashed_password: str | None) -> bool:
    try:
        encoded = password.encode("utf-8")
        if len(encoded) > 72:
            return False
        matches = bcrypt.checkpw(encoded, (hashed_password or _DUMMY_HASH).encode("ascii"))
    except (ValueError, UnicodeError):
        return False
    return hashed_password is not None and matches


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)},
        JWT_SECRET_KEY, algorithm=ALGORITHM,
    )


def decode_access_token(token: str) -> UUID:
    payload = jwt.decode(
        token, JWT_SECRET_KEY, algorithms=[ALGORITHM],
        options={"require": ["sub", "iat", "exp"]},
    )
    return UUID(payload["sub"])
