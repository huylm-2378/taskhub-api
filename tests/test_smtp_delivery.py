"""Optional real SMTP delivery to a local Mailpit inbox; never relay to real users."""
import os
import socket
from time import monotonic, sleep
from uuid import UUID, uuid4

import httpx
import pytest

import config
from database import SessionLocal
from models import Comment, Project, Task, User
from security import create_access_token


@pytest.fixture
def smtp_task(anonymous_client, monkeypatch):
    settings = {
        "EMAIL_ENABLED": True, "SMTP_HOST": "127.0.0.1",
        "SMTP_PORT": int(os.getenv("MAILPIT_SMTP_PORT", "1025")),
        "SMTP_USERNAME": "", "SMTP_PASSWORD": "", "SMTP_FROM": "taskhub@example.com",
        "SMTP_USE_TLS": False, "SMTP_USE_SSL": False, "SMTP_TIMEOUT_SECONDS": 2,
    }
    for name, value in settings.items():
        monkeypatch.setattr(config, name, value)
    with SessionLocal() as db:
        suffix = uuid4().hex
        users = {name: User(name=name, email=f"{name}_{suffix}@example.com", hashed_password="test-hash")
                 for name in ("owner", "assignee", "author")}
        task = Task(title="SMTP delivery", project=Project(name="SMTP", owner=users["owner"]),
                    assignee=users["assignee"])
        db.add_all([*users.values(), task])
        db.commit()
        return anonymous_client, task.id, users


@pytest.mark.skipif(not os.getenv("MAILPIT_HTTP_URL"), reason="Set MAILPIT_HTTP_URL to run real SMTP delivery test")
def test_comment_delivered_to_real_smtp_inbox(smtp_task):
    client, task_id, users = smtp_task
    headers = {"Authorization": f"Bearer {create_access_token(users['author'].id)}"}
    response = client.post(f"/api/tasks/{task_id}/comments", headers=headers,
                           json={"content": "Đã kiểm tra gửi email qua SMTP"})
    assert response.status_code == 201, response.text
    comment_id = response.json()["id"]
    with SessionLocal() as db:
        assert db.get(Comment, UUID(comment_id)) is not None
    with httpx.Client(base_url=os.environ["MAILPIT_HTTP_URL"], timeout=5) as inbox:
        deadline = monotonic() + 5
        while True:
            listing = inbox.get("/api/v1/messages", params={"limit": 100})
            listing.raise_for_status()
            messages = [m for m in listing.json()["messages"] if str(task_id) in m["Subject"]]
            if len(messages) == 2 or monotonic() >= deadline:
                break
            sleep(0.1)
        assert len(messages) == 2
        recipients = set()
        for message in messages:
            detail = inbox.get(f"/api/v1/message/{message['ID']}")
            detail.raise_for_status()
            mail = detail.json()
            assert "Đã kiểm tra gửi email qua SMTP" in mail["Text"]
            assert comment_id in mail["Text"] and str(task_id) in mail["Text"]
            assert len(mail["To"]) == 1
            recipients.add(mail["To"][0]["Address"])
        assert recipients == {users["owner"].email, users["assignee"].email}


def test_real_smtp_connection_failure_preserves_comment(smtp_task, monkeypatch, caplog):
    client, task_id, users = smtp_task
    # Reserve a loopback port without listening: a real SMTP connection is refused.
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        monkeypatch.setattr(config, "SMTP_PORT", reserved.getsockname()[1])
        headers = {"Authorization": f"Bearer {create_access_token(users['author'].id)}"}
        response = client.post(f"/api/tasks/{task_id}/comments", headers=headers,
                               json={"content": "Saved even when SMTP is down"})
    assert response.status_code == 201, response.text
    with SessionLocal() as db:
        assert db.get(Comment, UUID(response.json()["id"])).content == "Saved even when SMTP is down"
    errors = [r for r in caplog.records if "Comment email failed" in r.getMessage()]
    assert len(errors) == 2  # A failed recipient must not prevent the second attempt.
