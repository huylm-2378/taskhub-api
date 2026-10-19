from datetime import UTC, datetime, timedelta
import logging
from uuid import UUID

import bcrypt
import jwt

from config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_IAT_LEEWAY_SECONDS, JWT_SECRET_KEY

if len(JWT_SECRET_KEY.encode("utf-8")) < 32:
    raise RuntimeError("Set JWT_SECRET_KEY to a random secret of at least 32 bytes in .env.")

ALGORITHM = "HS256"
logger = logging.getLogger("taskhub.auth")


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
        # Validate iat below with a small, bounded clock tolerance. Keep PyJWT's
        # signature, exp and nbf checks strict; global leeway would extend expiry.
        options={"require": ["sub", "iat", "exp"], "verify_iat": False},
    )
    issued_at = payload["iat"]
    if not isinstance(issued_at, int) or isinstance(issued_at, bool):
        raise jwt.InvalidIssuedAtError("Issued At claim (iat) must be an integer.")
    skew = issued_at - datetime.now(UTC).timestamp()
    if skew > JWT_IAT_LEEWAY_SECONDS:
        logger.warning("JWT issued in future: clock_skew_seconds=%.3f", skew)
        raise jwt.ImmatureSignatureError("The token is not yet valid (iat)")
    return UUID(payload["sub"])
