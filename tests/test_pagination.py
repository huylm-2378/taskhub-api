from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from database import SessionLocal
from models import Project, Tag, User
from routers.pagination import Pagination, get_pagination, get_task_pagination


def test_default_pagination():
    assert get_pagination() == Pagination(offset=0, limit=20)
    assert get_task_pagination() == Pagination(offset=0, limit=20)


@pytest.mark.parametrize("skip, offset, expected", [
    (0, None, 0), (5, None, 5), (0, 5, 5), (5, 5, 5), (0, 0, 0),
])
def test_task_pagination_resolves_legacy_offset(skip, offset, expected):
    assert get_task_pagination(skip=skip, offset=offset, limit=7) == Pagination(expected, 7)


@pytest.mark.parametrize("skip, offset", [(1, 2), (1, 0)])
def test_task_pagination_rejects_conflicting_offsets(skip, offset):
    with pytest.raises(HTTPException) as caught:
        get_task_pagination(skip=skip, offset=offset)
    assert caught.value.status_code == 422


@pytest.fixture
def pagination_project(client):
    with SessionLocal() as db:
        owner = User(name="Owner", username="page_owner", email="page@example.com")
        project = Project(name="Pagination", owner=owner)
        db.add(project)
        db.commit()
        return str(project.id)


@pytest.mark.parametrize("path", [
    "/api/users", "/api/tags", "/api/projects", "/api/tasks", "/api/projects/{project_id}/tasks",
])
@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 101}, {"limit": "bad"}, {"offset": -1}, {"offset": "bad"},
])
def test_shared_pagination_validation(client, pagination_project, path, params):
    response = client.get(path.format(project_id=pagination_project), params=params)
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("path", ["/api/tasks", "/api/projects/{project_id}/tasks"])
def test_task_pagination_aliases_and_boundaries(client, pagination_project, path):
    path = path.format(project_id=pagination_project)
    for params in ({"skip": -1}, {"skip": "bad"}, {"skip": 1, "offset": 2}):
        assert client.get(path, params=params).status_code == 422
    for params in ({"skip": 5}, {"offset": 5}, {"skip": 5, "offset": 5}):
        response = client.get(path, params={**params, "limit": 100})
        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0, "offset": 5, "limit": 100}


@pytest.mark.parametrize("collection", ["users", "tags"])
def test_user_and_tag_pages_include_total_and_stable_order(client, collection):
    path = f"/api/{collection}"
    assert client.get(path).json() == {"items": [], "total": 0, "offset": 0, "limit": 20}

    # Equal timestamps require the UUID tie-breaker to keep pages stable.
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    with SessionLocal() as db:
        if collection == "users":
            records = [User(name=f"User {i}", username=f"page_{i}",
                            email=f"page_{i}@example.com", created_at=created_at)
                       for i in range(5)]
        else:
            records = [Tag(name=f"Tag {i}", created_at=created_at) for i in range(5)]
        db.add_all(records)
        db.commit()
        expected_ids = sorted(str(record.id) for record in records)

    full_page = client.get(path).json()
    assert full_page["total"] == 5
    assert full_page["offset"] == 0 and full_page["limit"] == 20
    assert [item["id"] for item in full_page["items"]] == expected_ids
    for offset, limit in ((0, 2), (2, 2), (4, 2), (5, 2), (8, 2), (0, 100)):
        response = client.get(path, params={"offset": offset, "limit": limit})
        assert response.status_code == 200
        assert response.json() == {
            "items": full_page["items"][offset:offset + limit],
            "total": 5, "offset": offset, "limit": limit,
        }


@pytest.mark.parametrize("collection", ["users", "tags"])
def test_user_and_tag_total_tracks_api_creation(client, collection):
    path = f"/api/{collection}"
    assert client.get(path).json()["total"] == 0
    payload = {"name": "Created"}
    if collection == "users":
        payload.update(username="created", email="created@example.com")
    created = client.post(path, json=payload)
    assert created.status_code == 201, created.text
    assert client.get(path).json() == {
        "items": [created.json()], "total": 1, "offset": 0, "limit": 20,
    }
    assert client.get(path, params={"offset": 1}).json() == {
        "items": [], "total": 1, "offset": 1, "limit": 20,
    }


def test_task_total_tracks_create_and_delete(client, pagination_project):
    path = f"/api/projects/{pagination_project}/tasks"
    created = client.post(path, json={"title": "Count me"})
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    for endpoint in (path, "/api/tasks"):
        page = client.get(endpoint, params={"skip": 1}).json()
        assert page == {"items": [], "total": 1, "offset": 1, "limit": 20}
    assert client.delete(f"/api/tasks/{task_id}").status_code == 204
    for endpoint in (path, "/api/tasks"):
        page = client.get(endpoint).json()
        assert page == {"items": [], "total": 0, "offset": 0, "limit": 20}
