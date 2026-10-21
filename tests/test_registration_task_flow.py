from uuid import UUID

import pytest

from database import SessionLocal
from models import Project, Task, User


@pytest.mark.parametrize("nested", [False, True], ids=["tasks", "project-tasks"])
def test_register_login_create_project_and_task(anonymous_client, nested):
    # anonymous_client is a real TestClient: no JWT/dependency/CRUD overrides.
    client = anonymous_client
    credentials = {"username": "new_member", "password": "integration-password"}
    response = client.post("/api/users/register", json={
        **credentials, "name": "New member", "email": "member@example.com",
    })
    assert response.status_code == 201, response.text
    user = response.json()
    assert user["role"] == "USER" and user["is_active"] is True
    assert "password" not in response.text
    response = client.post("/api/users/login", data=credentials)
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    response = client.post("/api/projects", headers=headers, json={"name": "Integration", "owner_id": user["id"]})
    assert response.status_code == 201, response.text
    project = response.json()
    path = f"/api/projects/{project['id']}/tasks" if nested else "/api/tasks"
    body = {"title": "First task", "assignee_id": user["id"], "priority": 4}
    if not nested:
        body["project_id"] = project["id"]
    assert client.post(path, json=body).status_code == 401
    response = client.post(path, headers=headers, json=body)
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["project_id"] == project["id"]
    assert task["status"] == "TODO"
    assert task["assignee_id"] == user["id"]
    fetched = client.get(f"/api/tasks/{task['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "First task"
    listed = client.get("/api/tasks?status=TODO&priority=HIGH", headers=headers)
    assert [entry["id"] for entry in listed.json()["items"]] == [task["id"]]
    assert listed.json()["total"] == 1
    with SessionLocal() as db:
        stored_user = db.get(User, UUID(user["id"]))
        assert stored_user.hashed_password != credentials["password"]
        assert db.get(Project, UUID(project["id"])).owner_id == stored_user.id
        stored_task = db.get(Task, UUID(task["id"]))
        assert stored_task.assignee_id == stored_user.id
        assert stored_task.project_id == UUID(project["id"])
