from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select

from database import SessionLocal
from models import Bookmark, Project, Tag, Task, User, UserRole

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


def test_global_tags_require_admin_for_writes(anonymous_client, actors):
    client = anonymous_client
    admin_headers = actors["admin"][1]
    response = client.post("/api/tags", headers=admin_headers, json={"name": "backend"})
    assert response.status_code == 201, response.text
    tag = response.json()
    path = f"/api/tags/{tag['id']}"

    for headers in ({}, {"Authorization": "Bearer invalid"}):
        assert client.get("/api/tags", headers=headers).status_code == 401
        assert client.post("/api/tags", headers=headers, json={"name": "Forbidden"}).status_code == 401
        assert client.patch(path, headers=headers, json={"name": "Forbidden"}).status_code == 401

    for actor in ("owner", "other"):
        headers = actors[actor][1]
        project = create_project(client, actors[actor])
        assert client.post("/api/tags", headers=headers, json={"name": "Forbidden"}).status_code == 403
        assert client.patch(path, headers=headers, json={"name": "Forbidden"}).status_code == 403
        listed = client.get("/api/tags", headers=headers)
        assert listed.status_code == 200
        assert listed.json() == [tag]
        # Project ownership permits using an existing global tag, not renaming it.
        response = client.post(f"/api/projects/{project['id']}/tasks", headers=headers, json={
            "title": "Tagged task", "tag_ids": [tag["id"]],
        })
        assert response.status_code == 201, response.text
        assert response.json()["tags"] == [tag]

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Tag)) == 1
        assert db.get(Tag, UUID(tag["id"])).name == "backend"

    renamed = client.patch(path, headers=admin_headers, json={"name": "frontend"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json() == {**tag, "name": "frontend"}
    assert client.get("/api/tags", headers=actors["owner"][1]).json() == [renamed.json()]


@pytest.mark.parametrize("change", [{"role": UserRole.USER}, {"is_active": False}])
def test_tag_write_permissions_follow_current_admin_state(anonymous_client, actors, change):
    client = anonymous_client
    admin, headers = actors["admin"]
    response = client.post("/api/tags", headers=headers, json={"name": "backend"})
    assert response.status_code == 201, response.text
    tag = response.json()

    with SessionLocal() as db:
        user = db.get(User, UUID(admin["id"]))
        for field, value in change.items():
            setattr(user, field, value)
        db.commit()

    # Reuse the existing JWT after demotion/deactivation.
    assert client.post("/api/tags", headers=headers, json={"name": "Forbidden"}).status_code == 403
    assert client.patch(f"/api/tags/{tag['id']}", headers=headers, json={"name": "Forbidden"}).status_code == 403
    expected_read_status = 403 if "is_active" in change else 200
    assert client.get("/api/tags", headers=headers).status_code == expected_read_status
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Tag)) == 1
        assert db.get(Tag, UUID(tag["id"])).name == "backend"


def test_user_summaries_and_collections_use_active_user_permissions(anonymous_client, actors):
    client = anonymous_client
    owner, owner_headers = actors["owner"]
    other, other_headers = actors["other"]
    project = create_project(client, actors["owner"])
    task_response = client.post(f"/api/projects/{project['id']}/tasks", headers=owner_headers, json={
        "title": "Assigned task", "assignee_id": owner["id"],
    })
    assert task_response.status_code == 201, task_response.text
    summary = {key: owner[key] for key in ("id", "created_at", "name", "username")}
    responses = {
        f"/api/users/{owner['id']}": summary,
        f"/api/users/{owner['username'].upper()}/profile": summary,
        f"/api/projects?owner_id={owner['id']}": {
            "items": [project], "total": 1, "offset": 0, "limit": 20,
        },
        f"/api/tasks?assignee_id={owner['id']}": {
            "items": [
                {key: value for key, value in task_response.json().items() if key not in {"assignee", "tags"}}
            ],
            "total": 1, "offset": 0, "limit": 20,
        },
    }
    for path, expected in responses.items():
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer invalid"}).status_code == 401
        response = client.get(path, headers=other_headers)
        assert response.status_code == 200, response.text
        assert response.json() == expected
        assert owner["email"] not in response.text
    assert client.get("/api/users/me", headers=owner_headers).json()["email"] == owner["email"]
    assert client.get("/api/users", headers=other_headers).status_code == 403
    admin_list = client.get("/api/users", headers=actors["admin"][1])
    assert admin_list.status_code == 200
    assert owner["email"] in {item["email"] for item in admin_list.json()}
    with SessionLocal() as db:
        db.get(User, UUID(owner["id"])).is_active = False
        db.commit()
    for path, expected in responses.items():
        response = client.get(path, headers=other_headers)
        assert response.status_code == 200
        assert response.json() == expected
    with SessionLocal() as db:
        db.get(User, UUID(other["id"])).is_active = False
        db.commit()
    for path in responses:
        assert client.get(path, headers=other_headers).status_code == 403


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
    page = client.get(project_path + "/tasks", headers=other_headers).json()
    assert len(page["items"]) == page["total"] == 4
    # Transferring ownership immediately changes permission for existing tokens.
    assert client.patch(project_path, headers=actors["owner"][1], json={"owner_id": other["id"]}).status_code == 200
    assert client.patch(project_path, headers=actors["owner"][1], json={"name": "Old owner"}).status_code == 403
    assert client.patch(project_path, headers=other_headers, json={"name": "New owner"}).status_code == 200
    assert client.patch(f"/api/projects/{uuid4()}", headers=other_headers, json={"name": "Missing"}).status_code == 404


@pytest.mark.parametrize("operation, actor", [
    ("create", "admin"), ("update", "owner"), ("update", "admin"),
])
def test_inactive_project_owner_is_rejected_without_saving(anonymous_client, actors, operation, actor):
    client = anonymous_client
    project = create_project(client, actors["owner"])
    path = f"/api/projects/{project['id']}"
    target_id = actors["other"][0]["id"]
    with SessionLocal() as db:
        db.get(User, UUID(target_id)).is_active = False
        db.commit()

    body = {"name": "Must not be saved", "owner_id": target_id}
    headers = actors[actor][1]
    if operation == "create":
        response = client.post("/api/projects", headers=headers, json=body)
    else:
        response = client.patch(path, headers=headers, json=body)

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Owner is inactive"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Project)) == 1
        stored = db.get(Project, UUID(project["id"]))
        assert stored.name == project["name"]
        assert str(stored.owner_id) == project["owner_id"]
    assert client.get(path, headers=headers).json() == project

    # Reactivating the same target makes the same request valid.
    with SessionLocal() as db:
        db.get(User, UUID(target_id)).is_active = True
        db.commit()
    if operation == "create":
        response = client.post("/api/projects", headers=headers, json=body)
        assert response.status_code == 201, response.text
    else:
        response = client.patch(path, headers=headers, json=body)
        assert response.status_code == 200, response.text
    assert response.json()["owner_id"] == target_id


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


def test_unbookmark_is_idempotent_and_isolated_by_user_and_task(anonymous_client, actors):
    client = anonymous_client
    project = create_project(client, actors["owner"])
    task_ids = []
    for title in ("First", "Second"):
        response = client.post(
            f"/api/projects/{project['id']}/tasks",
            headers=actors["owner"][1], json={"title": title},
        )
        assert response.status_code == 201, response.text
        task_ids.append(UUID(response.json()["id"]))
    expected = set()
    for name in ("owner", "other"):
        user, headers = actors[name]
        for task_id in task_ids:
            response = client.post(f"/api/tasks/{task_id}/bookmark", headers=headers)
            assert response.status_code == 200, response.text
            expected.add((UUID(user["id"]), task_id))

    path = f"/api/tasks/{task_ids[0]}/bookmark"
    # An admin with no bookmark cannot delete anyone else's bookmark.
    response = client.delete(path, headers=actors["admin"][1])
    assert response.status_code == 204
    assert response.content == b""
    with SessionLocal() as db:
        assert set(db.execute(select(Bookmark.user_id, Bookmark.task_id)).all()) == expected

    # A regular user who does not manage the project can remove their own bookmark.
    expected.remove((UUID(actors["other"][0]["id"]), task_ids[0]))
    for _ in range(2):
        response = client.delete(path, headers=actors["other"][1])
        assert response.status_code == 204, response.text
        assert response.content == b""
        with SessionLocal() as db:
            assert set(db.execute(select(Bookmark.user_id, Bookmark.task_id)).all()) == expected
            assert db.get(Task, task_ids[0]) is not None
            assert db.get(Task, task_ids[1]) is not None

    response = client.post(path, headers=actors["other"][1])
    assert response.status_code == 200, response.text
    expected.add((UUID(actors["other"][0]["id"]), task_ids[0]))
    with SessionLocal() as db:
        assert set(db.execute(select(Bookmark.user_id, Bookmark.task_id)).all()) == expected


def test_unbookmark_errors_do_not_remove_bookmarks(anonymous_client, actors):
    client = anonymous_client
    project = create_project(client, actors["owner"])
    response = client.post(
        f"/api/projects/{project['id']}/tasks",
        headers=actors["owner"][1], json={"title": "Keep bookmarked"},
    )
    assert response.status_code == 201, response.text
    task_id = UUID(response.json()["id"])
    path = f"/api/tasks/{task_id}/bookmark"
    user, headers = actors["other"]
    assert client.post(path, headers=headers).status_code == 200

    for auth in ({}, {"Authorization": "Bearer invalid"}):
        response = client.delete(path, headers=auth)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
    response = client.delete(f"/api/tasks/{uuid4()}/bookmark", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"
    assert client.delete("/api/tasks/invalid/bookmark", headers=headers).status_code == 422

    with SessionLocal() as db:
        db.get(User, UUID(user["id"])).is_active = False
        db.commit()
    assert client.delete(path, headers=headers).status_code == 403
    with SessionLocal() as db:
        assert db.get(Bookmark, (UUID(user["id"]), task_id)) is not None
        assert db.get(Task, task_id) is not None
