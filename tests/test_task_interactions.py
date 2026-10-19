from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Bookmark, Comment, Project, Tag, Task, User, UserRole, task_tags
from schemas.task import TaskUpdate
from security import create_access_token, hash_password
from services import task_interactions


@pytest.fixture(scope="module")
def interaction_password_hash():
    return hash_password("interaction-test-password")


@pytest.fixture
def context(anonymous_client, interaction_password_hash):
    with SessionLocal() as db:
        users = {
            name: User(
                name=name, username=name, email=f"{name}@example.com",
                hashed_password=interaction_password_hash,
                role=UserRole.ADMIN if name == "admin" else UserRole.USER,
                is_active=name != "inactive",
            )
            for name in ("owner", "author", "assignee", "outsider", "other_pm", "admin", "inactive")
        }
        project = Project(name="Main", owner=users["owner"])
        other_project = Project(name="Other", owner=users["other_pm"])
        task = Task(title="Main task", project=project, assignee=users["assignee"])
        sibling = Task(title="Same project", project=project)
        other_task = Task(title="Other project", project=other_project)
        comment = Comment(content="Original", task=task, author=users["author"])
        db.add_all([*users.values(), task, sibling, other_task, comment])
        db.commit()
        return SimpleNamespace(
            client=anonymous_client, users=users, task_id=task.id, project_id=project.id,
            sibling_id=sibling.id, other_task_id=other_task.id, comment_id=comment.id,
            headers={name: {"Authorization": f"Bearer {create_access_token(user.id)}"} for name, user in users.items()},
        )


def test_assign_owner_admin_and_persisted_relations(context):
    ctx = context
    path = f"/api/tasks/{ctx.task_id}/assign"
    for actor, target in (("owner", "author"), ("admin", "outsider")):
        body = {"assignee_id": str(ctx.users[target].id)}
        response = ctx.client.post(path, headers=ctx.headers[actor], json=body)
        assert response.status_code == 200, response.text
        assert response.json()["assignee_id"] == body["assignee_id"]
        assert response.json()["title"] == "Main task"
        assert response.json()["status"] == "TODO"
        # Reassigning to the current assignee is a successful no-op.
        assert ctx.client.post(path, headers=ctx.headers[actor], json=body).json() == response.json()
        with SessionLocal() as db:
            assert db.get(Task, ctx.task_id).assignee_id == ctx.users[target].id
        nested = ctx.client.get(f"/api/projects/{ctx.project_id}/tasks", headers=ctx.headers[actor]).json()
        task = next(task for task in nested if task["id"] == str(ctx.task_id))
        assert task["assignee"]["id"] == body["assignee_id"]


def test_assign_rejects_unauthorized_missing_and_inactive_targets(context):
    ctx = context
    path = f"/api/tasks/{ctx.task_id}/assign"
    body = {"assignee_id": str(ctx.users["author"].id)}
    for actor in ("author", "assignee", "outsider", "other_pm", "inactive"):
        assert ctx.client.post(path, headers=ctx.headers[actor], json=body).status_code == 403
    for target, status in ((uuid4(), 404), (ctx.users["inactive"].id, 409)):
        response = ctx.client.post(path, headers=ctx.headers["owner"], json={"assignee_id": str(target)})
        assert response.status_code == status, response.text
    assert ctx.client.post(f"/api/tasks/{uuid4()}/assign", headers=ctx.headers["owner"], json=body).status_code == 404
    with SessionLocal() as db:
        assert db.get(Task, ctx.task_id).assignee_id == ctx.users["assignee"].id


@pytest.mark.parametrize("nested", [False, True], ids=["tasks", "project-tasks"])
def test_create_task_rejects_inactive_assignee_without_persisting(context, nested):
    ctx = context
    path = f"/api/projects/{ctx.project_id}/tasks" if nested else "/api/tasks"
    body = {"title": "Must not be saved", "assignee_id": str(ctx.users["inactive"].id)}
    if not nested:
        body["project_id"] = str(ctx.project_id)
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(Task))
    response = ctx.client.post(path, headers=ctx.headers["owner"], json=body)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Assignee is inactive"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Task)) == before
    # The failure must leave later requests usable.
    body["assignee_id"] = str(ctx.users["assignee"].id)
    assert ctx.client.post(path, headers=ctx.headers["owner"], json=body).status_code == 201


def test_create_comment_uses_authenticated_author(context):
    ctx = context
    path = f"/api/tasks/{ctx.task_id}/comments"
    response = ctx.client.post(path, headers=ctx.headers["outsider"], json={"content": "  New comment  "})
    assert response.status_code == 201, response.text
    comment = response.json()
    assert set(comment) == {"id", "created_at", "content", "task_id", "author_id"}
    assert comment["content"] == "New comment"
    assert comment["task_id"] == str(ctx.task_id)
    assert comment["author_id"] == str(ctx.users["outsider"].id)
    with SessionLocal() as db:
        stored = db.get(Comment, UUID(comment["id"]))
        assert stored.content == "New comment"
        assert stored.author_id == ctx.users["outsider"].id
    assert ctx.client.post(f"/api/tasks/{uuid4()}/comments", headers=ctx.headers["author"], json={"content": "Missing"}).status_code == 404


@pytest.mark.parametrize("actor", ["author", "owner", "admin"])
def test_author_project_owner_and_admin_can_edit_and_delete(context, actor):
    ctx = context
    path = f"/api/tasks/{ctx.task_id}/comments/{ctx.comment_id}"
    response = ctx.client.patch(path, headers=ctx.headers[actor], json={"content": "  Edited  "})
    assert response.status_code == 200, response.text
    assert response.json()["content"] == "Edited"
    assert response.json()["author_id"] == str(ctx.users["author"].id)
    assert response.json()["task_id"] == str(ctx.task_id)
    with SessionLocal() as db:
        assert db.get(Comment, ctx.comment_id).content == "Edited"
    response = ctx.client.delete(path, headers=ctx.headers[actor])
    assert response.status_code == 204, response.text
    assert response.content == b""
    with SessionLocal() as db:
        assert db.get(Comment, ctx.comment_id) is None
        assert db.get(Task, ctx.task_id) is not None
    assert ctx.client.delete(path, headers=ctx.headers[actor]).status_code == 404


def test_comment_permissions_do_not_follow_assignee_or_other_project(context):
    ctx = context
    path = f"/api/tasks/{ctx.task_id}/comments/{ctx.comment_id}"
    for actor in ("assignee", "outsider", "other_pm", "inactive"):
        assert ctx.client.patch(path, headers=ctx.headers[actor], json={"content": "Forbidden"}).status_code == 403
        assert ctx.client.delete(path, headers=ctx.headers[actor]).status_code == 403
    with SessionLocal() as db:
        assert db.get(Comment, ctx.comment_id).content == "Original"


def test_comment_must_belong_to_task_even_for_admin(context):
    ctx = context
    for actor in ("author", "owner", "admin", "other_pm"):
        for task_id in (ctx.sibling_id, ctx.other_task_id, uuid4()):
            path = f"/api/tasks/{task_id}/comments/{ctx.comment_id}"
            assert ctx.client.patch(path, headers=ctx.headers[actor], json={"content": "Wrong task"}).status_code == 404
            assert ctx.client.delete(path, headers=ctx.headers[actor]).status_code == 404
    path = f"/api/tasks/{ctx.task_id}/comments/{uuid4()}"
    assert ctx.client.delete(path, headers=ctx.headers["admin"]).status_code == 404
    assert ctx.client.patch(path, headers=ctx.headers["admin"], json={"content": "Missing"}).status_code == 404
    with SessionLocal() as db:
        assert db.get(Comment, ctx.comment_id).content == "Original"


def test_comment_permissions_follow_project_ownership_transfer(context):
    ctx = context
    response = ctx.client.patch(f"/api/projects/{ctx.project_id}", headers=ctx.headers["owner"], json={
        "owner_id": str(ctx.users["other_pm"].id),
    })
    assert response.status_code == 200
    path = f"/api/tasks/{ctx.task_id}/comments/{ctx.comment_id}"
    assert ctx.client.patch(path, headers=ctx.headers["owner"], json={"content": "Former PM"}).status_code == 403
    assert ctx.client.patch(path, headers=ctx.headers["other_pm"], json={"content": "New PM"}).status_code == 200


def test_interaction_auth_and_input_validation(context):
    ctx = context
    base = f"/api/tasks/{ctx.task_id}"
    requests = [
        ("post", base + "/assign", {"assignee_id": str(ctx.users["author"].id)}),
        ("post", base + "/comments", {"content": "New"}),
        ("patch", base + f"/comments/{ctx.comment_id}", {"content": "Edited"}),
        ("delete", base + f"/comments/{ctx.comment_id}", None),
    ]
    for method, path, body in requests:
        for headers, status in (({}, 401), ({"Authorization": "Bearer invalid"}, 401), (ctx.headers["inactive"], 403)):
            assert ctx.client.request(method, path, headers=headers, json=body).status_code == status
    for body in ({}, {"assignee_id": None}, {"assignee_id": "invalid"}, {
        "assignee_id": str(ctx.users["author"].id), "status": "DONE",
    }):
        assert ctx.client.post(base + "/assign", headers=ctx.headers["owner"], json=body).status_code == 422
    for body in ({}, {"content": None}, {"content": "  "}, {"content": "x" * 10001},
                 {"content": "Spoofed", "author_id": str(ctx.users["admin"].id)},
                 {"content": "Moved", "task_id": str(ctx.other_task_id)}):
        assert ctx.client.post(base + "/comments", headers=ctx.headers["author"], json=body).status_code == 422
        assert ctx.client.patch(base + f"/comments/{ctx.comment_id}", headers=ctx.headers["author"], json=body).status_code == 422
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Comment)) == 1
        assert db.get(Comment, ctx.comment_id).content == "Original"


def invoke_operation(db, ctx, operation):
    user = db.get(User, ctx.users["owner"].id)
    if operation == "assign":
        return task_interactions.assign_task(db, ctx.task_id, ctx.users["author"].id, user)
    if operation == "create":
        return task_interactions.add_comment(db, ctx.task_id, "New", user)
    if operation == "edit":
        return task_interactions.edit_comment(db, ctx.task_id, ctx.comment_id, "Edited", user)
    if operation == "update_task":
        return task_interactions.update_task(db, ctx.task_id, TaskUpdate(status="IN_PROGRESS"), user)
    if operation == "delete_task":
        return task_interactions.delete_task(db, ctx.task_id, user)
    return task_interactions.delete_comment(db, ctx.task_id, ctx.comment_id, user)


@pytest.mark.parametrize("operation", ["assign", "create", "edit", "delete", "update_task", "delete_task"])
@pytest.mark.parametrize("failure", ["integrity", "unexpected", "commit"])
def test_transaction_rolls_back_flushed_writes_and_session_is_reusable(context, operation, failure):
    ctx = context

    def fail(db, *args):
        if failure == "integrity":
            raise IntegrityError("injected constraint failure", {}, Exception("conflict"))
        raise RuntimeError("injected failure")

    # Fail after SQL was issued, or at commit after the explicit flush.
    event_name = "before_commit" if failure == "commit" else "after_flush_postexec"
    with SessionLocal() as db:
        event.listen(db, event_name, fail)
        try:
            with pytest.raises(HTTPException if failure == "integrity" else RuntimeError) as caught:
                invoke_operation(db, ctx, operation)
            if failure == "integrity":
                assert caught.value.status_code == 409
        finally:
            event.remove(db, event_name, fail)
        assert not db.in_transaction()
        assert db.get(Task, ctx.task_id).assignee_id == ctx.users["assignee"].id
        assert db.get(Task, ctx.task_id).status == "TODO"
        assert db.get(Comment, ctx.comment_id).content == "Original"
        assert db.scalar(select(func.count()).select_from(Comment)) == 1
        # The failed transaction was rolled back explicitly; this session works.
        invoke_operation(db, ctx, operation)
    with SessionLocal() as db:
        if operation == "assign":
            assert db.get(Task, ctx.task_id).assignee_id == ctx.users["author"].id
        elif operation == "create":
            assert db.scalar(select(func.count()).select_from(Comment)) == 2
        elif operation == "edit":
            assert db.get(Comment, ctx.comment_id).content == "Edited"
        elif operation == "update_task":
            assert db.get(Task, ctx.task_id).status == "IN_PROGRESS"
        elif operation == "delete_task":
            assert db.get(Task, ctx.task_id) is None
            assert db.get(Comment, ctx.comment_id) is None
        else:
            assert db.get(Comment, ctx.comment_id) is None


@pytest.mark.parametrize("actor", ["owner", "admin", "assignee"])
def test_task_status_lifecycle_and_invalid_transitions(context, actor):
    ctx = context
    path = f"/api/tasks/{ctx.task_id}"
    headers = ctx.headers[actor]
    assert ctx.client.patch(path, headers=headers, json={"status": "DONE"}).status_code == 409
    for status in ("TODO", "IN_PROGRESS", "IN_PROGRESS", "DONE", "DONE"):
        response = ctx.client.patch(path, headers=headers, json={"status": status})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == status
        assert ctx.client.get(path, headers=headers).json()["status"] == status
    for status in ("TODO", "IN_PROGRESS"):
        assert ctx.client.patch(path, headers=headers, json={"status": status}).status_code == 409
    listed = ctx.client.get("/api/tasks", headers=headers, params={"status": "DONE"}).json()
    assert [task["id"] for task in listed] == [str(ctx.task_id)]


def test_task_partial_update_and_assignment_permissions(context):
    ctx = context
    path = f"/api/tasks/{ctx.task_id}"
    for actor in ("author", "outsider", "other_pm"):
        assert ctx.client.patch(path, headers=ctx.headers[actor], json={"status": "IN_PROGRESS"}).status_code == 403
    assert ctx.client.patch(path, headers=ctx.headers["assignee"], json={"title": "Forbidden", "status": "IN_PROGRESS"}).status_code == 403
    response = ctx.client.patch(path, headers=ctx.headers["owner"], json={
        "title": " Edited ", "description": "Details", "priority": 5,
        "due_date": "2027-01-01T10:00:00+07:00",
    })
    assert response.status_code == 200, response.text
    task = response.json()
    assert task["title"] == "Edited" and task["status"] == "TODO"
    assert task["priority"] == 5 and task["due_date"].startswith("2027-01-01T03:00:00")
    stored = ctx.client.get(path, headers=ctx.headers["owner"]).json()
    assert ctx.client.patch(path, headers=ctx.headers["owner"], json={}).json() == stored
    response = ctx.client.patch(path, headers=ctx.headers["admin"], json={"description": None, "due_date": None})
    assert response.json()["description"] is None and response.json()["due_date"] is None
    # A failed transition cannot partially save other field changes.
    assert ctx.client.patch(path, headers=ctx.headers["owner"], json={"title": "Do not save", "status": "DONE"}).status_code == 409
    assert ctx.client.get(path, headers=ctx.headers["owner"]).json()["title"] == "Edited"
    ctx.client.post(path + "/assign", headers=ctx.headers["owner"], json={"assignee_id": str(ctx.users["author"].id)})
    assert ctx.client.patch(path, headers=ctx.headers["assignee"], json={"status": "IN_PROGRESS"}).status_code == 403
    assert ctx.client.patch(path, headers=ctx.headers["author"], json={"status": "IN_PROGRESS"}).status_code == 200


@pytest.mark.parametrize("body", [
    {"title": None}, {"title": " "}, {"priority": None}, {"priority": 6},
    {"status": None}, {"status": "invalid"}, {"due_date": "2027-01-01T00:00:00"},
    {"project_id": str(uuid4())}, {"assignee_id": str(uuid4())}, {"tag_ids": []},
])
def test_task_update_rejects_invalid_fields(context, body):
    ctx = context
    response = ctx.client.patch(f"/api/tasks/{ctx.task_id}", headers=ctx.headers["owner"], json=body)
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("actor", ["owner", "admin"])
def test_delete_task_cascades_children_but_preserves_tags(context, actor):
    ctx = context
    with SessionLocal() as db:
        task = db.get(Task, ctx.task_id)
        tag = Tag(name="Keep this tag")
        task.tags.append(tag)
        db.add(Bookmark(user_id=ctx.users["author"].id, task_id=ctx.task_id))
        db.commit()
        tag_id = tag.id
    path = f"/api/tasks/{ctx.task_id}"
    for name in ("author", "assignee", "outsider", "other_pm"):
        assert ctx.client.delete(path, headers=ctx.headers[name]).status_code == 403
    response = ctx.client.delete(path, headers=ctx.headers[actor])
    assert response.status_code == 204 and response.content == b""
    assert ctx.client.delete(path, headers=ctx.headers[actor]).status_code == 404
    assert ctx.client.get(path, headers=ctx.headers[actor]).status_code == 404
    with SessionLocal() as db:
        assert db.get(Task, ctx.task_id) is None
        assert db.get(Comment, ctx.comment_id) is None
        assert db.scalar(select(func.count()).select_from(Bookmark)) == 0
        assert db.scalar(select(func.count()).select_from(task_tags)) == 0
        assert db.get(Tag, tag_id) is not None
        assert db.get(Project, ctx.project_id) is not None
        assert db.get(Task, ctx.sibling_id) is not None


def test_task_mutation_auth_missing_task_and_owner_transfer(context):
    ctx = context
    path = f"/api/tasks/{ctx.task_id}"
    for method, body in (("patch", {"status": "IN_PROGRESS"}), ("delete", None)):
        for headers, expected in (({}, 401), (ctx.headers["inactive"], 403)):
            assert ctx.client.request(method, path, headers=headers, json=body).status_code == expected
        assert ctx.client.request(method, f"/api/tasks/{uuid4()}", headers=ctx.headers["owner"], json=body).status_code == 404
    ctx.client.patch(f"/api/projects/{ctx.project_id}", headers=ctx.headers["owner"],
                     json={"owner_id": str(ctx.users["other_pm"].id)})
    assert ctx.client.patch(path, headers=ctx.headers["owner"], json={"title": "Former owner"}).status_code == 403
    assert ctx.client.delete(path, headers=ctx.headers["owner"]).status_code == 403
    assert ctx.client.patch(path, headers=ctx.headers["other_pm"], json={"title": "New owner"}).status_code == 200
    assert ctx.client.delete(path, headers=ctx.headers["other_pm"]).status_code == 204


def test_database_conflict_is_409_and_does_not_persist_comment(context):
    ctx = context

    def fail(db, flush_context):
        raise IntegrityError("injected constraint failure", {}, Exception("conflict"))

    event.listen(Session, "after_flush_postexec", fail)
    try:
        response = ctx.client.post(f"/api/tasks/{ctx.task_id}/comments", headers=ctx.headers["author"], json={"content": "Failed"})
        assert response.status_code == 409, response.text
    finally:
        event.remove(Session, "after_flush_postexec", fail)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Comment)) == 1
