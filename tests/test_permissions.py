from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select

from database import SessionLocal
from models import Bookmark, Task, User, UserRole

PASSWORD = "permission-test-password"


@pytest.fixture
def actors(anonymous_client):
    actors = {}
    for name in ("owner", "other", "admin"):
        response = anonymous_client.post("/api/users/register", json={
            "name": name, "username": name, "email": f"{name}@example.com", "password": PASSWORD,
        })
        assert response.status_code == 201, response.text
        user = response.json()
        response = anonymous_client.post("/api/users/login", data={"username": name, "password": PASSWORD})
        assert response.status_code == 200, response.text
        actors[name] = (user, {"Authorization": f"Bearer {response.json()['access_token']}"})
    # Promote after issuing JWT: permissions must be read from the database.
    with SessionLocal() as db:
        db.get(User, UUID(actors["admin"][0]["id"])).role = UserRole.ADMIN
        db.commit()
    return actors


def create_project(client, actor):
    user, headers = actor
    response = client.post("/api/projects", headers=headers, json={"name": "Owned", "owner_id": user["id"]})
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_dependencies_and_no_self_promotion(anonymous_client, actors):
    client = anonymous_client
    owner, headers = actors["owner"]
    admin, admin_headers = actors["admin"]
    body = {"name": "Legacy", "email": "legacy@example.com"}
    assert client.get("/api/users", headers=headers).status_code == 403
    assert client.post("/api/users", headers=headers, json=body).status_code == 403
    assert client.get("/api/users", headers=admin_headers).status_code == 200
    assert client.post("/api/users", headers=admin_headers, json=body).status_code == 201
    for changes in ({"role": "ADMIN"}, {"is_active": True}):
        assert client.put("/api/users/me", headers=headers, json=changes).status_code == 422
        response = client.post("/api/users/register", json={
            "name": "Injected", "username": "injected", "email": "injected@example.com",
            "password": PASSWORD, **changes,
        })
        assert response.status_code == 422
        assert client.post("/api/users", headers=admin_headers, json={**body, **changes}).status_code == 422
    with SessionLocal() as db:
        db.get(User, UUID(admin["id"])).role = UserRole.USER
        db.commit()
    assert client.get("/api/users", headers=admin_headers).status_code == 403
    assert client.get("/api/users/me", headers=headers).json()["role"] == "USER"


def test_project_manager_permissions_on_both_task_routes(anonymous_client, actors):
    client = anonymous_client
    project = create_project(client, actors["owner"])
    project_path = f"/api/projects/{project['id']}"
    other, other_headers = actors["other"]
    assert client.post("/api/projects", headers=other_headers, json={
        "name": "Spoofed owner", "owner_id": actors["owner"][0]["id"],
    }).status_code == 403
    for actor, expected in (("other", 403), ("owner", 201), ("admin", 201)):
        headers = actors[actor][1]
        assert client.post(project_path + "/tasks", headers=headers, json={"title": actor}).status_code == expected
        assert client.post("/api/tasks", headers=headers, json={
            "title": actor, "project_id": project["id"], "assignee_id": other["id"],
        }).status_code == expected
        assert client.patch(project_path, headers=headers, json={"name": actor}).status_code == (403 if actor == "other" else 200)
    # Being an assignee does not confer project management rights.
    assert client.post(project_path + "/tasks", headers=other_headers, json={"title": "Forbidden"}).status_code == 403
    assert len(client.get(project_path + "/tasks", headers=other_headers).json()) == 4
    # Transferring ownership immediately changes permission for existing tokens.
    assert client.patch(project_path, headers=actors["owner"][1], json={"owner_id": other["id"]}).status_code == 200
    assert client.patch(project_path, headers=actors["owner"][1], json={"name": "Old owner"}).status_code == 403
    assert client.patch(project_path, headers=other_headers, json={"name": "New owner"}).status_code == 200
    assert client.patch(f"/api/projects/{uuid4()}", headers=other_headers, json={"name": "Missing"}).status_code == 404


def test_inactive_user_cannot_login_or_use_existing_token(anonymous_client, actors):
    client = anonymous_client
    project = create_project(client, actors["owner"])
    task = client.post(f"/api/projects/{project['id']}/tasks", headers=actors["owner"][1], json={"title": "Task"}).json()
    admin, headers = actors["admin"]
    with SessionLocal() as db:
        db.get(User, UUID(admin["id"])).is_active = False
        db.commit()
    assert client.post("/api/users/login", data={"username": "admin", "password": PASSWORD}).status_code == 403
    for path in ("/api/users/me", "/api/users", "/api/tasks", "/api/projects", "/api/tags"):
        assert client.get(path, headers=headers).status_code == 403
    assert client.put("/api/users/me", headers=headers, json={"name": "Blocked"}).status_code == 403
    assert client.post(f"/api/tasks/{task['id']}/bookmark", headers=headers).status_code == 403
    assert client.patch(f"/api/projects/{project['id']}", headers=headers, json={"name": "Blocked"}).status_code == 403
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Bookmark)) == 0


def test_bookmark_auth_persistence_duplicates_and_user_isolation(anonymous_client, actors):
    client = anonymous_client
    project = create_project(client, actors["owner"])
    task = client.post(f"/api/projects/{project['id']}/tasks", headers=actors["owner"][1], json={"title": "Task"}).json()
    path = f"/api/tasks/{task['id']}/bookmark"
    for headers in ({}, {"Authorization": "Bearer invalid"}):
        response = client.post(path, headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
    for name in ("owner", "other"):
        user, headers = actors[name]
        first = client.post(path, headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["user_id"] == user["id"]
        assert first.json()["task_id"] == task["id"]
        assert client.post(path, headers=headers).json() == first.json()
    assert client.post(f"/api/tasks/{uuid4()}/bookmark", headers=actors["owner"][1]).status_code == 404
    assert client.post("/api/tasks/invalid/bookmark", headers=actors["owner"][1]).status_code == 422
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Bookmark)) == 2
        db.execute(delete(User).where(User.id == UUID(actors["other"][0]["id"])))
        db.commit()
        assert db.scalar(select(func.count()).select_from(Bookmark)) == 1
        db.execute(delete(Task).where(Task.id == UUID(task["id"])))
        db.commit()
        assert db.scalar(select(func.count()).select_from(Bookmark)) == 0
