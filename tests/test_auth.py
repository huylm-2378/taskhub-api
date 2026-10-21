from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from sqlalchemy import select

from config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_SECRET_KEY
from database import SessionLocal
from models import Tag, User
from security import ALGORITHM, create_access_token, verify_password

PASSWORD = "a valid password!"


def register(client, **changes):
    return client.post("/api/users/register", json={
        "name": "Huy", "username": "huy", "email": "huy@example.com", "password": PASSWORD, **changes,
    })


def login(client, username="huy", password=PASSWORD):
    return client.post("/api/users/login", data={"username": username, "password": password})


def authorization(client):
    response = login(client)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_register_login_and_current_user(anonymous_client):
    client = anonymous_client
    response = register(client, username=" HUY ", name=" Huy ")
    assert response.status_code == 201, response.text
    user = response.json()
    assert user["username"] == "huy"
    assert user["name"] == "Huy"
    assert set(user) == {"id", "created_at", "name", "username", "email", "role", "is_active"}
    assert user["role"] == "USER" and user["is_active"] is True
    with SessionLocal() as db:
        stored = db.get(User, UUID(user["id"]))
        assert stored.hashed_password.startswith("$2b$12$")
        assert stored.hashed_password != PASSWORD
        assert verify_password(PASSWORD, stored.hashed_password)
    response = login(client, username="HUY")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["token_type"] == "bearer"
    token = response.json()["access_token"]
    payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == user["id"]
    assert payload["exp"] - payload["iat"] == ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert set(payload) == {"sub", "iat", "exp"}
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/users/me", headers=headers).json() == user
    assert client.get("/api/users", headers=headers).status_code == 403
    for path in ["/api/users/huy/profile"]:
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        assert "hashed_password" not in response.text and "password" not in response.text


def test_update_me_only_changes_current_user_and_token_survives_rename(anonymous_client):
    client = anonymous_client
    user = register(client).json()
    other = register(client, username="other", email="other@example.com").json()
    headers = authorization(client)
    response = client.put("/api/users/me", headers=headers, json={"name": " Huy Updated ", "username": " NEW_HUY "})
    assert response.status_code == 200, response.text
    updated = {**user, "name": "Huy Updated", "username": "new_huy"}
    assert response.json() == updated
    assert client.get("/api/users/me", headers=headers).json() == updated
    assert client.get(f"/api/users/{other['id']}", headers=headers).json() == {
        key: other[key] for key in ("id", "created_at", "name", "username")
    }
    assert client.put("/api/users/me", headers=headers, json={}).json() == updated
    assert login(client).status_code == 401
    assert login(client, username="new_huy").status_code == 200
    response = client.put("/api/users/me", headers=headers, json={"email": "new@example.com"})
    assert response.status_code == 200
    assert response.json()["email"] == "new@example.com"


def test_duplicate_registration_and_update_rollback(anonymous_client):
    client = anonymous_client
    user = register(client).json()
    assert register(client, email="different@example.com").status_code == 409
    assert register(client, username="different").status_code == 409
    assert register(client, username="other", email="other@example.com").status_code == 201
    headers = authorization(client)
    for change in [{"username": "other"}, {"email": "other@example.com"}]:
        assert client.put("/api/users/me", headers=headers, json={"name": "Do not save", **change}).status_code == 409
        assert client.get("/api/users/me", headers=headers).json() == user
    assert client.put("/api/users/me", headers=headers, json={"name": "Saved"}).status_code == 200


@pytest.mark.parametrize("password", ["short", "x" * 73, "á" * 37, None])
def test_invalid_passwords(anonymous_client, password):
    assert register(anonymous_client, password=password).status_code == 422
    with SessionLocal() as db:
        assert db.scalar(select(User)) is None


def test_password_whitespace_and_unicode_are_preserved(anonymous_client):
    client = anonymous_client
    password = "  mật khẩu test  "
    assert register(client, password=password).status_code == 201
    assert login(client, password=password).status_code == 200
    assert login(client, password=password.strip()).status_code == 401


def test_login_errors_and_legacy_profiles(anonymous_client):
    client = anonymous_client
    assert register(client).status_code == 201
    with SessionLocal() as db:
        db.add(User(name="Legacy", username="legacy", email="legacy@example.com"))
        db.commit()
    for username, password in [("huy", "wrong"), ("missing", PASSWORD), ("legacy", PASSWORD), ("huy", "x" * 73)]:
        response = login(client, username, password)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["detail"] == "Incorrect username or password"
    assert client.post("/api/users/login", json={"username": "huy", "password": PASSWORD}).status_code == 422


@pytest.mark.parametrize("kind", ["expired", "wrong_signature", "wrong_algorithm", "no_exp", "no_sub", "no_iat", "bad_sub", "unknown_user", "future_iat", "malformed"])
def test_invalid_tokens(anonymous_client, kind):
    client = anonymous_client
    user = register(client).json()
    now = datetime.now(UTC)
    claims = {"sub": user["id"], "iat": now, "exp": now + timedelta(minutes=30)}
    key, algorithm = JWT_SECRET_KEY, ALGORITHM
    if kind == "expired":
        claims["exp"] = now - timedelta(seconds=1)
    elif kind == "wrong_signature":
        key = "different-signing-key-that-is-at-least-32-bytes"
    elif kind == "wrong_algorithm":
        algorithm = "HS384"
    elif kind.startswith("no_"):
        claims.pop(kind.removeprefix("no_"))
    elif kind == "bad_sub":
        claims["sub"] = "not-a-uuid"
    elif kind == "unknown_user":
        claims["sub"] = str(uuid4())
    elif kind == "future_iat":
        claims["iat"] = now + timedelta(hours=1)
    token = "not.a.token" if kind == "malformed" else jwt.encode(claims, key, algorithm=algorithm)
    response = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401, response.text
    assert response.headers["www-authenticate"] == "Bearer"


def test_tokens_cannot_authenticate_legacy_or_deleted_users(anonymous_client):
    client = anonymous_client
    user = register(client).json()
    headers = authorization(client)
    with SessionLocal() as db:
        db.delete(db.get(User, UUID(user["id"])))
        legacy = User(name="Legacy", username="legacy", email="legacy@example.com")
        db.add(legacy)
        db.commit()
        legacy_token = create_access_token(legacy.id)
    assert client.get("/api/users/me", headers=headers).status_code == 401
    assert client.get("/api/users/me", headers={"Authorization": f"Bearer {legacy_token}"}).status_code == 401


def test_update_rejects_invalid_and_sensitive_fields(anonymous_client):
    client = anonymous_client
    user = register(client).json()
    headers = authorization(client)
    for data in [
        {"name": None}, {"email": None}, {"username": None}, {"name": " "},
        {"email": "invalid"}, {"username": "bad name"}, {"id": str(uuid4())},
        {"password": "new password"}, {"hashed_password": "injected"}, {"is_admin": True},
    ]:
        assert client.put("/api/users/me", headers=headers, json=data).status_code == 422
    assert client.get("/api/users/me", headers=headers).json() == user


def test_all_data_routes_require_bearer_auth_and_swagger_describes_it(anonymous_client):
    client = anonymous_client
    schema = client.get("/openapi.json").json()
    public = {"/api/users/register", "/api/users/login"}
    for path, operations in schema["paths"].items():
        if not path.startswith("/api/") or path in public:
            continue
        concrete_path = path
        for param in ["user_id", "project_id", "task_id", "tag_id", "comment_id"]:
            concrete_path = concrete_path.replace("{" + param + "}", str(uuid4()))
        concrete_path = concrete_path.replace("{username}", "someone")
        for method, operation in operations.items():
            assert {"OAuth2PasswordBearer": []} in operation["security"]
            response = client.request(method, concrete_path, json={} if method in {"post", "put", "patch"} else None)
            assert response.status_code == 401, (path, method, response.text)
            assert response.headers["www-authenticate"] == "Bearer"
    for path in public:
        assert not schema["paths"][path]["post"].get("security")
    flow = schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]["password"]
    assert flow["tokenUrl"] == "api/users/login"
    assert client.get("/api/users/me", headers={"Authorization": "Basic invalid"}).status_code == 401
    assert client.get("/docs").status_code == 200
    assert client.get("/health").status_code == 200


def test_authenticated_taskhub_workflow(anonymous_client):
    client = anonymous_client
    user = register(client).json()
    headers = authorization(client)
    project_response = client.post("/api/projects", headers=headers, json={"name": "Private", "owner_id": user["id"]})
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    # Seed the shared catalog; this workflow stays authenticated as a regular user.
    with SessionLocal() as db:
        tag = Tag(name="backend")
        db.add(tag)
        db.commit()
        tag_id = str(tag.id)
    tags_response = client.get("/api/tags", headers=headers)
    assert tags_response.status_code == 200
    assert [tag["id"] for tag in tags_response.json()] == [tag_id]
    response = client.post(f"/api/projects/{project['id']}/tasks", headers=headers, json={
        "title": "Authenticated task", "assignee_id": user["id"], "tag_ids": [tag_id],
    })
    assert response.status_code == 201, response.text
    assert response.json()["tags"] == tags_response.json()
    assert "hashed_password" not in response.text
    assert client.get("/api/tasks", headers=headers).status_code == 200
    assert client.get(f"/api/projects/{project['id']}/tasks", headers=headers).status_code == 200
