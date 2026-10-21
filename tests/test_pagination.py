import pytest
from fastapi import HTTPException

from database import SessionLocal
from models import Project, User
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


def test_user_and_tag_lists_keep_array_responses(client, pagination_project):
    for path in ("/api/users", "/api/tags"):
        response = client.get(path, params={"limit": 100})
        assert response.status_code == 200
        assert isinstance(response.json(), list)


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
