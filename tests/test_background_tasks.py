from unittest.mock import MagicMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import config
from database import SessionLocal
from main import app
from models import Comment, Project, Task, User
from security import create_access_token
from services import notifications


@pytest.fixture
def mail_context(anonymous_client, monkeypatch):
    monkeypatch.setattr(config, "EMAIL_ENABLED", True)
    # These tests exercise authentication with signed JWTs; login is covered
    # by the registration integration tests. No external SMTP is contacted.
    with SessionLocal() as db:
        users = {name: User(name=name, email=f"{name}@example.com", hashed_password="unused-test-hash")
                 for name in ("owner", "assignee", "author")}
        task = Task(title="Task notification", project=Project(name="Mail", owner=users["owner"]), assignee=users["assignee"])
        db.add_all([*users.values(), task])
        db.commit()
        headers = {"Authorization": f"Bearer {create_access_token(users['author'].id)}"}
        send = Mock()
        monkeypatch.setattr(notifications, "send_email", send)
        return anonymous_client, task.id, users, headers, send


def test_background_email_runs_after_response_and_commit(mail_context):
    _, task_id, users, headers, send = mail_context
    response_finished = False
    verified = []

    async def record_response(scope, receive, send_message):
        async def record(message):
            nonlocal response_finished
            await send_message(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                response_finished = True
        await app(scope, receive, record)

    def verify_send(recipient, subject, body):
        assert response_finished
        # A separate DB connection must see the committed comment already.
        with SessionLocal() as db:
            comment = db.scalar(select(Comment).where(Comment.task_id == task_id))
            assert comment is not None and comment.content == "Ready to review"
            assert str(comment.id) in body
        assert "Task notification" in body and "author" in body
        assert str(task_id) in subject
        verified.append(recipient)

    send.side_effect = verify_send
    with TestClient(record_response) as client:
        response = client.post(f"/api/tasks/{task_id}/comments", headers=headers, json={"content": "Ready to review"})
    assert response.status_code == 201, response.text
    assert send.call_count == 2
    assert len(verified) == 2
    assert {call.args[0] for call in send.call_args_list} == {users["owner"].email, users["assignee"].email}


@pytest.mark.parametrize("scenario,expected", [
    ("same_recipient", {"owner@example.com"}),
    ("author_is_owner", {"assignee@example.com"}),
    ("inactive", {"owner@example.com"}),
    ("unassigned", {"owner@example.com"}),
    ("no_recipients", set()),
])
def test_recipient_selection(mail_context, scenario, expected):
    client, task_id, users, headers, send = mail_context
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if scenario == "same_recipient":
            task.assignee_id = users["owner"].id
        elif scenario == "author_is_owner":
            headers = {"Authorization": f"Bearer {create_access_token(users['owner'].id)}"}
        elif scenario == "inactive":
            db.get(User, users["assignee"].id).is_active = False
        elif scenario == "unassigned":
            task.assignee_id = None
        elif scenario == "no_recipients":
            task.assignee_id = users["author"].id
            task.project.owner_id = users["author"].id
        db.commit()
    assert client.post(f"/api/tasks/{task_id}/comments", headers=headers, json={"content": "Hello"}).status_code == 201
    assert {call.args[0] for call in send.call_args_list} == expected
    assert send.call_count == len(expected)


def test_disabled_or_deleted_comment_sends_no_email(mail_context, monkeypatch):
    client, task_id, _, headers, send = mail_context
    monkeypatch.setattr(config, "EMAIL_ENABLED", False)
    response = client.post(f"/api/tasks/{task_id}/comments", headers=headers, json={"content": "Saved"})
    assert response.status_code == 201
    send.assert_not_called()
    monkeypatch.setattr(config, "EMAIL_ENABLED", True)
    notifications.notify_comment(uuid4())
    send.assert_not_called()


def test_smtp_failure_keeps_comment_and_attempts_other_recipient(mail_context, caplog):
    client, task_id, _, headers, send = mail_context
    send.side_effect = [TimeoutError("private SMTP reply"), None]
    response = client.post(f"/api/tasks/{task_id}/comments", headers=headers, json={"content": "Private content"})
    assert response.status_code == 201
    assert send.call_count == 2
    with SessionLocal() as db:
        assert db.get(Comment, UUID(response.json()["id"])).content == "Private content"
    assert "Comment email failed" in caplog.text
    assert "private SMTP reply" not in caplog.text and "Private content" not in caplog.text


def test_failed_requests_never_schedule_email(mail_context, monkeypatch):
    client, task_id, _, headers, _ = mail_context
    notify = Mock()
    monkeypatch.setattr(notifications, "notify_comment", notify)
    path = f"/api/tasks/{task_id}/comments"
    assert client.post(path, json={"content": "Unauthorized"}).status_code == 401
    assert client.post(path, headers=headers, json={"content": " "}).status_code == 422
    assert client.post(f"/api/tasks/{uuid4()}/comments", headers=headers, json={"content": "Missing"}).status_code == 404

    def fail(db, flush_context):
        raise IntegrityError("test", {}, Exception("conflict"))

    event.listen(Session, "after_flush_postexec", fail)
    try:
        assert client.post(path, headers=headers, json={"content": "Rollback"}).status_code == 409
    finally:
        event.remove(Session, "after_flush_postexec", fail)
    notify.assert_not_called()
    with SessionLocal() as db:
        assert db.scalar(select(Comment)) is None


@pytest.mark.parametrize("transport", ["starttls", "ssl", "plain"])
def test_smtp_transport_configuration_and_message(monkeypatch, transport):
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(config, "SMTP_PORT", 465 if transport == "ssl" else 587)
    monkeypatch.setattr(config, "SMTP_FROM", "taskhub@example.com")
    monkeypatch.setattr(config, "SMTP_USERNAME", "smtp-user" if transport != "plain" else "")
    monkeypatch.setattr(config, "SMTP_PASSWORD", "smtp-test-password")
    monkeypatch.setattr(config, "SMTP_USE_SSL", transport == "ssl")
    monkeypatch.setattr(config, "SMTP_USE_TLS", transport == "starttls")
    smtp_constructor = Mock()
    monkeypatch.setattr(notifications.smtplib, "SMTP_SSL" if transport == "ssl" else "SMTP", smtp_constructor)
    # MagicMock supplies the context manager used by smtplib.SMTP.
    connection = MagicMock()
    smtp_constructor.return_value = connection
    smtp = connection.__enter__.return_value
    notifications.send_email("recipient@example.com", "TaskHub comment", "Nội dung comment")
    assert smtp_constructor.call_args.kwargs["timeout"] == config.SMTP_TIMEOUT_SECONDS
    assert smtp.starttls.call_count == (1 if transport == "starttls" else 0)
    assert smtp.login.call_count == (0 if transport == "plain" else 1)
    message = smtp.send_message.call_args.args[0]
    assert message["From"] == "taskhub@example.com"
    assert message["To"] == "recipient@example.com"
    assert message["Subject"] == "TaskHub comment"
    assert "Nội dung comment" in message.get_content()
    connection.__exit__.assert_called_once()
