import pytest


@pytest.fixture
def task_lists(client):
    owner = client.post(
        "/api/users", json={"name": "Owner", "email": "owner@example.com"}
    ).json()
    other = client.post(
        "/api/users", json={"name": "Other", "email": "other@example.com"}
    ).json()
    projects = [
        client.post(
            "/api/projects", json={"name": name, "owner_id": owner["id"]}
        ).json()
        for name in ("Main", "Other")
    ]
    tags = [
        client.post("/api/tags", json={"name": name}).json()["id"]
        for name in ("backend", "urgent")
    ]

    for project in projects:
        for index in range(18):
            response = client.post(
                f"/api/projects/{project['id']}/tasks",
                json={
                    "title": f"Task {index}",
                    "priority": index % 5 + 1,
                    "tag_ids": tags,
                    "assignee_id": (owner["id"], other["id"], None, owner["id"])[index % 4],
                },
            )
            assert response.status_code == 201, response.text

            if index % 3 == 0:
                task_id = response.json()["id"]
                for status in ("IN_PROGRESS", "DONE"):
                    updated = client.patch(
                        f"/api/tasks/{task_id}",
                        json={"status": status},
                    )
                    assert updated.status_code == 200, updated.text
    return projects


def test_combined_filters_before_pagination(client, task_lists):
    project_id = task_lists[0]["id"]
    for path, scope in (
        ("/api/tasks", {"project_id": project_id}),
        (f"/api/projects/{project_id}/tasks", {}),
    ):
        full_page = client.get(path, params={**scope, "limit": 100}).json()
        all_tasks = full_page["items"]
        assert full_page["total"] == 18
        assert len(all_tasks) == 18
        for priority, values in (("LOW", (1, 2)), ("MEDIUM", (3,)), ("HIGH", (4, 5))):
            query = {**scope, "status": "TODO", "priority": priority}
            expected = [
                task
                for task in all_tasks
                if task["status"] == "TODO" and task["priority"] in values
            ]
            assert expected
            assert client.get(path, params=query).json() == {
                "items": expected, "total": len(expected), "offset": 0, "limit": 20,
            }
            assert (
                client.get(path, params={**query, "skip": 1, "limit": 2}).json()
                == {"items": expected[1:3], "total": len(expected), "offset": 1, "limit": 2}
            )
        assert (
            client.get(path, params={**scope, "skip": 10, "limit": 5}).json()
            == {"items": all_tasks[10:15], "total": 18, "offset": 10, "limit": 5}
        )
        assert (
            client.get(path, params={**scope, "offset": 10, "limit": 5}).json()
            == {"items": all_tasks[10:15], "total": 18, "offset": 10, "limit": 5}
        )
        assert client.get(path, params={**scope, "skip": 100}).json() == {
            "items": [], "total": 18, "offset": 100, "limit": 20,
        }
        assert client.get(path, params={**scope, "status": "IN_PROGRESS"}).json() == {
            "items": [], "total": 0, "offset": 0, "limit": 20,
        }
    # Without project scope, combine filters across both projects.
    response = client.get("/api/tasks?status=TODO&priority=HIGH")
    assert response.status_code == 200
    assert {task["project_id"] for task in response.json()["items"]} == {
        project["id"] for project in task_lists
    }


@pytest.mark.parametrize(
    "params",
    [
        {"skip": -1},
        {"skip": "bad"},
        {"limit": 0},
        {"limit": 101},
        {"priority": "URGENT"},
        {"status": "invalid"},
        {"skip": 1, "offset": 2},
    ],
)
def test_invalid_filters(client, params):
    assert client.get("/api/tasks", params=params).status_code == 422


def test_assignee_combines_with_other_filters_before_pagination(client, task_lists):
    response = client.get("/api/tasks", params={"limit": 100})
    assert response.status_code == 200
    all_tasks = response.json()["items"]
    assert response.json()["total"] == 36
    assert any(task["assignee_id"] is None for task in all_tasks)
    assignee_id = task_lists[0]["owner_id"]
    for scope in ({}, {"project_id": task_lists[0]["id"]}):
        query = {"assignee_id": assignee_id, "status": "TODO", "priority": "HIGH", **scope}
        expected = [
            task for task in all_tasks
            if task["assignee_id"] == assignee_id
            and task["status"] == "TODO"
            and task["priority"] in (4, 5)
            and (not scope or task["project_id"] == scope["project_id"])
        ]
        assert len(expected) >= 2
        assert client.get("/api/tasks", params=query).json() == {
            "items": expected, "total": len(expected), "offset": 0, "limit": 20,
        }
        for page_name in ("skip", "offset"):
            response = client.get("/api/tasks", params={**query, page_name: 1, "limit": 1})
            assert response.status_code == 200
            assert response.json() == {
                "items": expected[1:2], "total": len(expected), "offset": 1, "limit": 1,
            }
        assert client.get("/api/tasks", params={**query, "skip": 1, "offset": 2}).status_code == 422


def test_query_parameters_in_openapi(client):
    schema = client.get("/openapi.json").json()
    for path in ("/api/tasks", "/api/projects/{project_id}/tasks"):
        params = {
            param["name"]: param for param in schema["paths"][path]["get"]["parameters"]
        }
        for name in ("skip", "limit", "status", "priority"):
            assert params[name]["in"] == "query"
        assert params["offset"]["deprecated"] is True
    for path, filter_name in (("/api/projects", "owner_id"), ("/api/tasks", "assignee_id")):
        params = {param["name"]: param for param in schema["paths"][path]["get"]["parameters"]}
        assert params[filter_name]["in"] == "query"
        assert params[filter_name]["required"] is False
        assert {"type": "string", "format": "uuid"} in params[filter_name]["schema"]["anyOf"]
