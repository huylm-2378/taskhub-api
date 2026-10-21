from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from database import SessionLocal
from models import Project, Tag, Task, User


@pytest.fixture
def user_collections(client):
    with SessionLocal() as db:
        owner = User(name="Owner", username="owner", email="owner@example.com")
        other = User(name="Other", username="other", email="other@example.com")
        empty = User(name="Empty", username="empty", email="empty@example.com")
        external = Project(name="External", owner=other)
        tags = [Tag(name=name) for name in ("backend", "urgent", "web")]
        db.add_all([owner, other, empty, external, *tags])
        created_at = datetime(2026, 1, 1, tzinfo=UTC)
        projects, tasks = [], []
        # Insert in reverse ID order with timestamp ties to exercise both sort keys.
        for index in reversed(range(23)):
            timestamp = created_at + timedelta(days=index % 2)
            project = Project(
                id=UUID(int=index + 1), name=f"Project {index}", owner=owner,
                created_at=timestamp,
            )
            task = Task(
                id=UUID(int=index + 1), title=f"Task {index}", assignee=owner,
                project=external if index % 2 else project,
                tags=tags, created_at=timestamp,
            )
            db.add_all([project, task])
            projects.append(project)
            tasks.append(task)
        db.add_all([
            Task(title="Someone else's task", project=projects[0], assignee=other),
            Task(title="Unassigned task", project=projects[0]),
        ])
        expected = {
            "projects": [str(item.id) for item in sorted(projects, key=lambda item: (item.created_at, item.id))],
            "tasks": [str(item.id) for item in sorted(tasks, key=lambda item: (item.created_at, item.id))],
        }
        db.commit()
        return str(owner.id), str(empty.id), expected


@pytest.mark.parametrize("collection, filter_name, page_name", [
    ("projects", "owner_id", "offset"), ("tasks", "assignee_id", "skip"),
])
def test_user_filters_scope_order_and_pagination(client, user_collections, collection, filter_name, page_name):
    owner_id, _, expected = user_collections
    path = f"/api/{collection}"
    scope = {filter_name: owner_id}
    default_page = client.get(path, params=scope)
    assert default_page.status_code == 200, default_page.text
    assert [item["id"] for item in default_page.json()["items"]] == expected[collection][:20]
    assert default_page.json() == {
        "items": default_page.json()["items"], "total": 23, "offset": 0, "limit": 20,
    }

    response = client.get(path, params={**scope, "limit": 100})
    assert response.status_code == 200, response.text
    all_items = response.json()["items"]
    assert response.json() == {"items": all_items, "total": 23, "offset": 0, "limit": 100}
    assert [item["id"] for item in all_items] == expected[collection]
    for offset in range(0, 25, 5):
        page = client.get(path, params={**scope, page_name: offset, "limit": 5})
        assert page.status_code == 200
        assert page.json() == {
            "items": all_items[offset:offset + 5], "total": 23, "offset": offset, "limit": 5,
        }
    for offset in (23, 40):
        assert client.get(path, params={**scope, page_name: offset}).json() == {
            "items": [], "total": 23, "offset": offset, "limit": 20,
        }
    if collection == "tasks":
        assert client.get(path, params={**scope, "offset": 5, "limit": 5}).json() == {
            "items": all_items[5:10], "total": 23, "offset": 5, "limit": 5,
        }
    unfiltered = client.get(path, params={"limit": 100})
    assert unfiltered.status_code == 200
    assert len(unfiltered.json()["items"]) == (24 if collection == "projects" else 25)
    assert unfiltered.json()["total"] == (24 if collection == "projects" else 25)

    for item in all_items:
        if collection == "projects":
            assert item["owner_id"] == owner_id
            assert "tasks" not in item
        else:
            assert item["assignee_id"] == owner_id
            assert "assignee" not in item
            assert "tags" not in item

    # Filtering historical data must not require the target user to be active.
    with SessionLocal() as db:
        db.get(User, UUID(owner_id)).is_active = False
        db.commit()
    assert client.get(path, params={**scope, "limit": 100}).json() == {
        "items": all_items, "total": 23, "offset": 0, "limit": 100,
    }


@pytest.mark.parametrize("collection, filter_name, page_name", [
    ("projects", "owner_id", "offset"), ("tasks", "assignee_id", "skip"),
])
def test_user_filters_empty_missing_and_invalid_input(client, user_collections, collection, filter_name, page_name):
    owner_id, empty_id, _ = user_collections
    path = f"/api/{collection}"
    for user_id in (empty_id, str(uuid4())):
        empty = client.get(path, params={filter_name: user_id})
        assert empty.status_code == 200
        assert empty.json() == {"items": [], "total": 0, "offset": 0, "limit": 20}
    assert client.get(path, params={filter_name: "invalid"}).status_code == 422
    for query in (
        {page_name: -1}, {page_name: "invalid"},
        {"limit": 0}, {"limit": 101}, {"limit": "invalid"},
    ):
        response = client.get(path, params={filter_name: owner_id, **query})
        assert response.status_code == 422, response.text


@pytest.mark.parametrize("collection", ["projects", "assigned-tasks"])
def test_old_user_collection_routes_are_removed(client, user_collections, collection):
    owner_id, _, _ = user_collections
    response = client.get(f"/api/users/{owner_id}/{collection}")
    assert response.status_code == 404
