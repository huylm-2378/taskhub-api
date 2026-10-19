from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

import security
from config import JWT_SECRET_KEY


@pytest.fixture
def jwt_clock(monkeypatch):
    now = datetime(2026, 10, 19, 12, 0, 0, tzinfo=UTC)

    class DateType(type):
        def __instancecheck__(cls, value):
            return isinstance(value, datetime)

    class Clock(datetime, metaclass=DateType):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)

    monkeypatch.setattr(security, "datetime", Clock)
    monkeypatch.setattr(jwt.api_jwt, "datetime", Clock)

    def move(seconds):
        nonlocal now
        now += timedelta(seconds=seconds)

    return now, move


def test_new_token_survives_small_backward_clock_step(jwt_clock):
    _, move = jwt_clock
    user_id = uuid4()
    token = security.create_access_token(user_id)
    move(-2)
    assert security.decode_access_token(token) == user_id


@pytest.mark.parametrize("seconds", [0, 1])
def test_expiration_has_no_clock_grace(jwt_clock, seconds):
    now, _ = jwt_clock
    token = jwt.encode({"sub": str(uuid4()), "iat": now - timedelta(minutes=30),
                        "exp": now - timedelta(seconds=seconds)}, JWT_SECRET_KEY, algorithm=security.ALGORITHM)
    with pytest.raises(jwt.ExpiredSignatureError):
        security.decode_access_token(token)


def test_clock_skew_boundary_and_diagnostic_without_token(jwt_clock, caplog):
    _, move = jwt_clock
    token = security.create_access_token(uuid4())
    move(-5)
    security.decode_access_token(token)
    move(-1)
    with pytest.raises(jwt.ImmatureSignatureError):
        security.decode_access_token(token)
    assert "clock_skew_seconds=6" in caplog.text
    assert token not in caplog.text and JWT_SECRET_KEY not in caplog.text


@pytest.mark.parametrize("iat", [None, True, "invalid", "123", 123.5])
def test_invalid_issued_at_is_rejected(jwt_clock, iat):
    now, _ = jwt_clock
    token = jwt.encode({"sub": str(uuid4()), "iat": iat, "exp": now + timedelta(minutes=30)},
                       JWT_SECRET_KEY, algorithm=security.ALGORITHM)
    expected = jwt.MissingRequiredClaimError if iat is None else jwt.InvalidIssuedAtError
    with pytest.raises(expected):
        security.decode_access_token(token)


def test_not_before_stays_strict(jwt_clock):
    now, _ = jwt_clock
    token = jwt.encode({"sub": str(uuid4()), "iat": now, "nbf": now + timedelta(seconds=1),
                        "exp": now + timedelta(minutes=30)}, JWT_SECRET_KEY, algorithm=security.ALGORITHM)
    with pytest.raises(jwt.ImmatureSignatureError):
        security.decode_access_token(token)


def test_issued_at_tolerance_can_be_disabled(jwt_clock, monkeypatch):
    _, move = jwt_clock
    monkeypatch.setattr(security, "JWT_IAT_LEEWAY_SECONDS", 0)
    token = security.create_access_token(uuid4())
    move(-1)
    with pytest.raises(jwt.ImmatureSignatureError):
        security.decode_access_token(token)
