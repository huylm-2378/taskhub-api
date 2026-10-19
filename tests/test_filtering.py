import pytest


@pytest.fixture
def task_lists(client):
    owner = client.post("/api/users", json={"name": "Owner", "email": "owner@example.com"}).json()
    projects = [client.post("/api/projects", json={"name": name, "owner_id": owner["id"]}).json() for name in ("Main", "Other")]
    tags = [client.post("/api/tags", json={"name": name}).json()["id"] for name in ("backend", "urgent")]
    for project in projects:
        for index in range(18):
            response = client.post(f"/api/projects/{project['id']}/tasks", json={
                "title": f"Task {index}", "priority": index % 5 + 1,
                "status": "TODO" if index % 3 else "DONE", "tag_ids": tags,
            })
            assert response.status_code == 201, response.text
    return projects


def test_combined_filters_before_pagination(client, task_lists):
    project_id = task_lists[0]["id"]
    for path, scope in (("/api/tasks", {"project_id": project_id}), (f"/api/projects/{project_id}/tasks", {})):
        all_tasks = client.get(path, params={**scope, "limit": 100}).json()
        assert len(all_tasks) == 18
        for priority, values in (("LOW", (1, 2)), ("MEDIUM", (3,)), ("HIGH", (4, 5))):
            query = {**scope, "status": "TODO", "priority": priority}
            expected = [task for task in all_tasks if task["status"] == "TODO" and task["priority"] in values]
            assert expected
            assert client.get(path, params=query).json() == expected
            assert client.get(path, params={**query, "skip": 1, "limit": 2}).json() == expected[1:3]
        assert client.get(path, params={**scope, "skip": 10, "limit": 5}).json() == all_tasks[10:15]
        assert client.get(path, params={**scope, "offset": 10, "limit": 5}).json() == all_tasks[10:15]
        assert client.get(path, params={**scope, "skip": 100}).json() == []
        assert client.get(path, params={**scope, "status": "IN_PROGRESS"}).json() == []
    # Without project scope, combine filters across both projects.
    response = client.get("/api/tasks?status=TODO&priority=HIGH")
    assert response.status_code == 200
    assert {task["project_id"] for task in response.json()} == {project["id"] for project in task_lists}


@pytest.mark.parametrize("params", [
    {"skip": -1}, {"skip": "bad"}, {"limit": 0}, {"limit": 101},
    {"priority": "URGENT"}, {"status": "invalid"}, {"skip": 1, "offset": 2},
])
def test_invalid_filters(client, params):
    assert client.get("/api/tasks", params=params).status_code == 422


def test_query_parameters_in_openapi(client):
    schema = client.get("/openapi.json").json()
    for path in ("/api/tasks", "/api/projects/{project_id}/tasks"):
        params = {param["name"]: param for param in schema["paths"][path]["get"]["parameters"]}
        for name in ("skip", "limit", "status", "priority"):
            assert params[name]["in"] == "query"
        assert params["offset"]["deprecated"] is True
