from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import event

from database import SessionLocal, engine
from models import Project, Tag, Task, User


@contextmanager
def count_selects():
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def create_context(client):
    user_response = client.post("/api/users", json={
        "name": "Huy", "email": "huy@example.com", "username": " Huy_Test ",
    })
    assert user_response.status_code == 201, user_response.text
    user = user_response.json()
    project = client.post("/api/projects", json={"name": "TaskHub", "owner_id": user["id"]}).json()
    tags = [client.post("/api/tags", json={"name": name}).json() for name in ["backend", "urgent"]]
    return user, project, tags


def test_create_project_task_with_relations_and_profile(client):
    user, project, tags = create_context(client)
    path = f"/api/projects/{project['id']}/tasks"
    assert client.get(path).json() == []
    response = client.post(path, json={
        "title": "Build API", "assignee_id": user["id"],
        "tag_ids": [tags[0]["id"], tags[1]["id"], tags[0]["id"]],
        "due_date": "2026-10-21T15:00:00+07:00",
    })
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["project_id"] == project["id"]
    assert task["assignee"] == user
    assert task["tags"] == tags
    assert task["due_date"].startswith("2026-10-21T08:00:00")
    listed = client.get(path)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1
    assert listed.json()[0]["tags"] == tags
    assert client.get(path, params={"status": "DONE"}).json() == []
    profile = client.get("/api/users/HUY_TEST/profile")
    assert profile.status_code == 200, profile.text
    data = profile.json()
    assert data["username"] == "huy_test"
    assert data["projects"] == [{**project, "tasks": listed.json()}]
    assert data["assigned_tasks"] == listed.json()


def test_project_task_pagination_and_scope(client):
    user, project, tags = create_context(client)
    path = f"/api/projects/{project['id']}/tasks"
    for index in range(3):
        response = client.post(path, json={"title": f"Task {index}", "tag_ids": [tag["id"] for tag in tags]})
        assert response.status_code == 201, response.text
        assert response.json()["assignee"] is None
    other = client.post("/api/projects", json={"name": "Other", "owner_id": user["id"]}).json()
    client.post(f"/api/projects/{other['id']}/tasks", json={"title": "Other task"})
    all_tasks = client.get(path).json()
    assert len(all_tasks) == 3
    assert len({task["id"] for task in all_tasks}) == 3
    for offset in range(3):
        page = client.get(path, params={"offset": offset, "limit": 1}).json()
        assert page == all_tasks[offset:offset + 1]
        assert len(page[0]["tags"]) == 2
    assert client.get(path, params={"offset": 3}).json() == []
    for query in [{"limit": 0}, {"offset": -1}, {"limit": 101}, {"status": "invalid"}]:
        assert client.get(path, params=query).status_code == 422


def test_invalid_nested_task_requests_are_atomic(client):
    _, project, tags = create_context(client)
    path = f"/api/projects/{project['id']}/tasks"
    for data, code in [
        ({"assignee_id": str(uuid4())}, 404),
        ({"tag_ids": [tags[0]["id"], str(uuid4())]}, 404),
        ({"tag_ids": ["invalid"]}, 422),
        ({"tag_ids": None}, 422),
        ({"tag_ids": [str(uuid4())] * 101}, 422),
        ({"project_id": str(uuid4())}, 422),
        ({"title": " "}, 422),
        ({"priority": 6}, 422),
        ({"due_date": "2026-10-21T15:00:00"}, 422),
    ]:
        response = client.post(path, json={"title": "Invalid", **data})
        assert response.status_code == code, response.text
    assert client.get(path).json() == []
    for project_id, code in [(str(uuid4()), 404), ("invalid", 422)]:
        missing_path = f"/api/projects/{project_id}/tasks"
        assert client.get(missing_path).status_code == code
        assert client.post(missing_path, json={"title": "Missing"}).status_code == code


def test_usernames_and_empty_profile(client):
    user, _, _ = create_context(client)
    assert user["username"] == "huy_test"
    duplicate = client.post("/api/users", json={
        "name": "Other", "email": "other@example.com", "username": "HUY_TEST",
    })
    assert duplicate.status_code == 409
    generated = client.post("/api/users", json={"name": "Other", "email": "other@example.com"})
    assert generated.status_code == 201
    generated_user = generated.json()
    assert generated_user["username"].startswith("user_")
    profile = client.get(f"/api/users/{generated_user['username']}/profile")
    assert profile.json() == {**generated_user, "projects": [], "assigned_tasks": []}
    assert client.get("/api/users/missing/profile").status_code == 404
    assert client.get("/api/users/a!/profile").status_code == 422
    for username in [None, "ab", "bad name", "x" * 65]:
        assert client.post("/api/users", json={
            "name": "Invalid", "email": "invalid@example.com", "username": username,
        }).status_code == 422


@pytest.mark.parametrize("size", [1, 12])
def test_nested_responses_have_bounded_queries(client, size):
    # Distinct assignees/tags prevent the identity map from hiding N+1 queries.
    with SessionLocal() as db:
        owner = User(name="Owner", email="owner@example.com", username="owner")
        other_owner = User(name="Other", email="other@example.com", username="other")
        project = Project(name="Main", owner=owner)
        external_project = Project(name="External", owner=other_owner)
        for index in range(size):
            assignee = User(name=f"User {index}", email=f"user{index}@example.com")
            tag = Tag(name=f"tag{index}")
            db.add(Task(title=f"Task {index}", project=project, assignee=assignee, tags=[tag]))
            owned_project = Project(name=f"Project {index}", owner=owner)
            db.add(Task(title=f"Owned {index}", project=owned_project, tags=[tag]))
            db.add(Task(title=f"Assigned {index}", project=external_project, assignee=owner, tags=[tag]))
        db.commit()
        project_id = project.id

    with count_selects() as statements:
        response = client.get(f"/api/projects/{project_id}/tasks", params={"limit": 100})
        assert response.status_code == 200, response.text
        assert len(response.json()) == size
        assert all(task["assignee"] and task["tags"] for task in response.json())
    assert len(statements) == 2

    with count_selects() as statements:
        response = client.get("/api/users/owner/profile")
        assert response.status_code == 200, response.text
        profile = response.json()
        assert len(profile["projects"]) == size + 1
        assert len(profile["assigned_tasks"]) == size
        assert sum(len(project["tasks"]) for project in profile["projects"]) == size * 2
    assert len(statements) == 4


def test_relationship_openapi(client):
    schema = client.get("/openapi.json").json()
    tasks_path = schema["paths"]["/api/projects/{project_id}/tasks"]
    assert "get" in tasks_path and "post" in tasks_path
    assert "/api/users/{username}/profile" in schema["paths"]
    fields = schema["components"]["schemas"]["ProjectTaskCreate"]["properties"]
    assert "tag_ids" in fields and "project_id" not in fields
