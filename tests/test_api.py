from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from database import SessionLocal
from models import Tag


def create_user(client):
    response = client.post(
        "/api/users", json={"name": "Huy", "email": "huy@example.com"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_project(client):
    user = create_user(client)
    response = client.post(
        "/api/projects", json={"name": "TaskHub", "owner_id": user["id"]}
    )
    assert response.status_code == 201, response.text
    return user, response.json()


def test_create_and_read_workflow(client):
    user, project = create_project(client)
    due_date = (datetime.now(UTC) + timedelta(days=1)).astimezone(
        timezone(timedelta(hours=7))
    )
    response = client.post(
        "/api/tasks",
        json={
            "title": "Build API",
            "project_id": project["id"],
            "assignee_id": user["id"],
            "due_date": due_date.isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    task = response.json()
    assert UUID(task["id"]).version == 4
    assert task["status"] == "TODO"
    assert task["priority"] == 3
    actual_due_date = datetime.fromisoformat(task["due_date"].replace("Z", "+00:00"))
    # SQLite drops timezone metadata from the UTC value stored by the schema.
    if actual_due_date.tzinfo is None:
        actual_due_date = actual_due_date.replace(tzinfo=UTC)
    assert actual_due_date == due_date.astimezone(UTC)
    for path, item in [("users", user), ("projects", project), ("tasks", task)]:
        expected = (
            {key: user[key] for key in ("id", "created_at", "name", "username")}
            if path == "users" else item
        )
        assert client.get(f"/api/{path}/{item['id']}").json() == expected
        listed = client.get(f"/api/{path}").json()
        assert listed == ([item] if path == "users" else {
            "items": [item], "total": 1, "offset": 0, "limit": 20,
        })
    assert client.get("/api/tasks", params={"status": "DONE"}).json() == {"items": [], "total": 0, "offset": 0, "limit": 20}
    assert client.get("/api/tasks", params={"project_id": str(uuid4())}).json() == {"items": [], "total": 0, "offset": 0, "limit": 20}
    assert client.get("/api/tasks", params={"offset": 1}).json() == {"items": [], "total": 1, "offset": 1, "limit": 20}


def test_duplicate_email_returns_conflict_and_next_request_works(client):
    create_user(client)
    duplicate = client.post(
        "/api/users", json={"name": "Other", "email": "huy@example.com"}
    )
    assert duplicate.status_code == 409
    assert len(client.get("/api/users").json()) == 1
    assert (
        client.post(
            "/api/users", json={"name": "Other", "email": "other@example.com"}
        ).status_code
        == 201
    )


@pytest.mark.parametrize("path", ["users", "projects", "tasks"])
def test_missing_and_invalid_ids_and_pagination(client, path):
    assert client.get(f"/api/{path}/{uuid4()}").status_code == 404
    assert client.get(f"/api/{path}/invalid").status_code == 422
    assert client.get(f"/api/{path}?limit=101").status_code == 422
    assert client.get(f"/api/{path}?offset=-1").status_code == 422


def test_missing_foreign_keys(client):
    assert (
        client.post(
            "/api/projects", json={"name": "Missing", "owner_id": str(uuid4())}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/tasks", json={"title": "Missing", "project_id": str(uuid4())}
        ).status_code
        == 404
    )
    _, project = create_project(client)
    assert (
        client.post(
            "/api/tasks",
            json={
                "title": "Missing assignee",
                "project_id": project["id"],
                "assignee_id": str(uuid4()),
            },
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "invalid",
    [
        {"priority": "Cao"},
        {"priority": 6},
        {"status": "INVALID"},
        {"title": "   "},
        {"due_date": "2026-10-21T15:00:00"},
    ],
)
def test_invalid_task_data(client, invalid):
    _, project = create_project(client)
    response = client.post(
        "/api/tasks",
        json={
            "title": "Build API",
            "project_id": project["id"],
            **invalid,
        },
    )
    assert response.status_code == 422
    assert client.get("/api/tasks").json() == {"items": [], "total": 0, "offset": 0, "limit": 20}


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("invalid", [
    {"status": "TODO"},
    {"status": "IN_PROGRESS"},
    {"status": "DONE"},
    {"due_date": "2000-01-01T00:00:00Z"},
])
def test_create_task_rejects_status_and_past_due_date(client, nested, invalid):
    _, project = create_project(client)
    path = f"/api/projects/{project['id']}/tasks" if nested else "/api/tasks"
    body = {"title": "New task", **invalid}
    if not nested:
        body["project_id"] = project["id"]

    response = client.post(path, json=body)

    assert response.status_code == 422, response.text
    assert client.get("/api/tasks").json() == {"items": [], "total": 0, "offset": 0, "limit": 20}


def test_user_validation(client):
    assert (
        client.post("/api/users", json={"name": "Huy", "email": "invalid"}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/users", json={"name": " ", "email": "huy@example.com"}
        ).status_code
        == 422
    )


def test_health_and_docs(anonymous_client):
    client = anonymous_client
    assert client.get("/health").json()["status"] == "Healthy"
    schema = client.get("/openapi.json").json()
    assert all(
        f"/api/{path}" in schema["paths"]
        for path in ["users", "projects", "tasks", "tags"]
    )
    assert not any(
        path == "/tasks" or path.startswith("/tasks/")
        for path in schema["paths"]
    )
    unbookmark = schema["paths"]["/api/tasks/{task_id}/bookmark"]["delete"]
    assert {"OAuth2PasswordBearer": []} in unbookmark["security"]
    assert "content" not in unbookmark["responses"]["204"]
    assert client.get("/docs").status_code == 200
    tag_items = schema["paths"]["/api/tags"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["items"]
    assert tag_items["$ref"] == "#/components/schemas/TagRead"


@pytest.mark.parametrize("path", [
    "/tasks", "/tasks/1", "/tasks/999", "/tasks/status/TODO",
    "/tasks/?limit=2", "/tasks/secure/1?keyword=hello",
])
def test_mock_routes_are_removed(anonymous_client, path):
    response = anonymous_client.get(path)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_list_tags_with_pagination(client):
    assert client.get("/api/tags").json() == []
    with SessionLocal() as db:
        db.add_all([Tag(name="backend"), Tag(name="urgent")])
        db.commit()

    response = client.get("/api/tags")
    assert response.status_code == 200
    tags = response.json()
    assert {tag["name"] for tag in tags} == {"backend", "urgent"}
    for tag in tags:
        assert UUID(tag["id"]).version == 4
        assert tag["created_at"]
        assert set(tag) == {"id", "created_at", "name"}
    assert client.get("/api/tags?limit=1").json() == tags[:1]
    assert client.get("/api/tags?offset=1&limit=1").json() == tags[1:]
    assert client.get("/api/tags?offset=2").json() == []


@pytest.mark.parametrize("query", ["offset=-1", "limit=0", "limit=101", "offset=abc"])
def test_invalid_tag_pagination(client, query):
    assert client.get(f"/api/tags?{query}").status_code == 422


def test_partial_project_update(client):
    _, project = create_project(client)
    path = f"/api/projects/{project['id']}"
    response = client.patch(path, json={"description": "First version"})
    assert response.status_code == 200
    assert response.json() == {**project, "description": "First version"}
    renamed = client.patch(path, json={"name": " Updated "}).json()
    assert renamed["name"] == "Updated"
    assert renamed["description"] == "First version"
    assert client.get(path).json() == renamed
    assert client.patch(path, json={}).json() == renamed
    cleared = client.patch(path, json={"description": None}).json()
    assert cleared == {**renamed, "description": None}
    owner = client.post(
        "/api/users", json={"name": "New owner", "email": "owner@example.com"}
    ).json()
    response = client.patch(path, json={"owner_id": owner["id"]})
    assert response.status_code == 200
    assert client.get(path).json()["owner_id"] == owner["id"]


def test_invalid_project_updates_leave_data_unchanged(client):
    _, project = create_project(client)
    path = f"/api/projects/{project['id']}"
    for data in [
        {"name": None},
        {"owner_id": None},
        {"name": " "},
        {"owner_id": "invalid"},
    ]:
        assert client.patch(path, json=data).status_code == 422
    assert (
        client.patch(
            path, json={"name": "Do not save", "owner_id": str(uuid4())}
        ).status_code
        == 404
    )
    assert client.get(path).json() == project
    assert (
        client.patch(f"/api/projects/{uuid4()}", json={"name": "Missing"}).status_code
        == 404
    )
    assert (
        client.patch("/api/projects/invalid", json={"name": "Missing"}).status_code
        == 422
    )


def test_create_update_tags_and_conflicts(client):
    response = client.post("/api/tags", json={"name": " backend "})
    assert response.status_code == 201
    tag = response.json()
    assert tag["name"] == "backend"
    assert client.post("/api/tags", json={"name": "backend"}).status_code == 409
    other_response = client.post("/api/tags", json={"name": "urgent"})
    assert other_response.status_code == 201
    other = other_response.json()
    path = f"/api/tags/{tag['id']}"
    assert client.patch(path, json={"name": "urgent"}).status_code == 409
    assert client.get("/api/tags").json() == [tag, other]
    response = client.patch(path, json={"name": " frontend "})
    assert response.status_code == 200
    updated = {**tag, "name": "frontend"}
    assert response.json() == updated
    assert client.patch(path, json={}).json() == updated
    assert client.get("/api/tags").json() == [updated, other]


def test_invalid_tag_writes(client):
    tag = client.post("/api/tags", json={"name": "backend"}).json()
    for data in [
        {"name": None},
        {"name": " "},
        {"name": "x" * 51},
        {"name": "backend", "extra": True},
    ]:
        assert client.post("/api/tags", json=data).status_code == 422
        assert client.patch(f"/api/tags/{tag['id']}", json=data).status_code == 422
    assert client.get("/api/tags").json() == [tag]
    assert (
        client.patch(f"/api/tags/{uuid4()}", json={"name": "missing"}).status_code
        == 404
    )
    assert (
        client.patch("/api/tags/invalid", json={"name": "missing"}).status_code == 422
    )
