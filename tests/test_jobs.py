from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import Mock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from celery.exceptions import Retry
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import config
from celery_app import celery_app
from database import SessionLocal
from models import Job, Project, Task, TaskStatus, User
from models.base import utc_now
from security import create_access_token
from services import jobs, notifications
from workers import tasks


@pytest.fixture
def context(anonymous_client, monkeypatch):
    publish = Mock()
    monkeypatch.setattr(celery_app, "send_task", publish)
    with SessionLocal.begin() as db:
        owner = User(name="Owner", email="owner@example.com", hashed_password="unused")
        stranger = User(name="Stranger", email="stranger@example.com", hashed_password="unused")
        project = Project(name="Report", owner=owner)
        task = Task(
            title='=HYPERLINK("https://example.com")', project=project, assignee=owner,
            due_date=utc_now() - timedelta(days=1),
        )
        db.add_all([task, stranger])
    headers = {"Authorization": f"Bearer {create_access_token(owner.id)}"}
    return anonymous_client, owner, stranger, project, task, headers, publish


def submit(context, key="report-1", project_id=None):
    client, _, _, project, _, headers, _ = context
    return client.post("/api/jobs/exports", headers=headers, json={
        "project_id": str(project_id or project.id), "idempotency_key": key,
    })


def test_export_roundtrip_replay_and_formula_safety(context):
    client, _, _, _, task, headers, publish = context
    response = submit(context)
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    assert response.json()["status"] == "pending"
    assert client.get(f"/api/jobs/{job_id}/download", headers=headers).status_code == 409
    assert submit(context).json()["id"] == job_id
    assert publish.call_count == 1
    assert tasks.run_job.apply(args=[job_id]).get()["status"] == "succeeded"
    assert tasks.execute_job(job_id)["status"] == "succeeded"
    result = client.get(f"/api/jobs/{job_id}", headers=headers)
    assert result.json()["attempts"] == 1
    assert "output" not in result.json() and "payload" not in result.json()
    download = client.get(f"/api/jobs/{job_id}/download", headers=headers)
    assert download.status_code == 200
    workbook = load_workbook(BytesIO(download.content))
    sheet = workbook.active
    assert sheet["A2"].value == str(task.id)
    assert sheet["B2"].value == task.title and sheet["B2"].data_type == "s"
    assert download.headers["content-disposition"].endswith('.xlsx"')


def test_key_conflict_scope_and_database_constraint(context):
    client, owner, stranger, _, _, headers, _ = context
    first = submit(context)
    with SessionLocal.begin() as db:
        other = Project(name="Other", owner_id=owner.id)
        db.add(other)
    assert submit(context, project_id=other.id).status_code == 409
    with SessionLocal.begin() as db:
        job = jobs.create_job(db, stranger.id, "export", "report-1", {"project_id": str(other.id)})
        assert str(job.id) != first.json()["id"]
    with pytest.raises(IntegrityError), SessionLocal.begin() as db:
        db.add(Job(owner_id=owner.id, kind="export", idempotency_key="report-1", payload={}))
    assert client.post("/api/jobs/exports", headers=headers, json={
        "project_id": str(other.id), "idempotency_key": " ",
    }).status_code == 422


def test_job_permissions_are_rechecked(context):
    client, owner, stranger, project, _, headers, _ = context
    job_id = submit(context).json()["id"]
    foreign_headers = {"Authorization": f"Bearer {create_access_token(stranger.id)}"}
    assert client.get(f"/api/jobs/{job_id}", headers=foreign_headers).status_code == 404
    assert client.get(f"/api/jobs/{job_id}/download", headers=foreign_headers).status_code == 404
    assert client.get(f"/api/jobs/{job_id}").status_code == 401
    assert client.post("/api/jobs/exports", headers=foreign_headers, json={
        "project_id": str(project.id), "idempotency_key": "denied",
    }).status_code == 403
    with SessionLocal.begin() as db:
        db.get(Project, project.id).owner_id = stranger.id
    assert tasks.execute_job(job_id)["status"] == "failed"
    assert client.get(f"/api/jobs/{job_id}/download", headers=headers).status_code == 403
    with SessionLocal() as db:
        assert db.get(Job, UUID(job_id)).error_code == "PermissionError"


def test_publish_outage_preserves_job_and_sweeper_recovers(context, caplog):
    _, _, _, _, _, _, publish = context
    publish.side_effect = ConnectionError("redis://secret-password")
    response = submit(context)
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert "secret-password" not in caplog.text
    with SessionLocal() as db:
        assert db.get(Job, UUID(job_id)).status == "pending"
    publish.side_effect = None
    assert jobs.dispatch_pending() == 1
    assert publish.call_args.kwargs["args"] == [job_id]
    assert publish.call_args.kwargs["queue"] == "heavy"
    assert jobs.dispatch_pending() == 0
    # Recover a lost publication once the re-delivery interval expires.
    with SessionLocal.begin() as db:
        db.get(Job, UUID(job_id)).available_at = utc_now() - timedelta(seconds=1)
    assert jobs.dispatch_pending() == 1
    assert tasks.execute_job(job_id)["status"] == "succeeded"
    assert jobs.dispatch_pending() == 0


def test_export_retry_then_success_and_bounded_failure(context, monkeypatch):
    job_id = submit(context).json()["id"]
    original = tasks.export_workbook
    render = Mock(side_effect=OSError("private error"))
    monkeypatch.setattr(tasks, "export_workbook", render)
    with pytest.raises(Retry):
        tasks.run_job.run(job_id)
    with SessionLocal() as db:
        job = db.get(Job, UUID(job_id))
        assert job.status == "pending" and job.output is None
        assert job.error_code == "OSError"
    monkeypatch.setattr(tasks, "export_workbook", original)
    assert tasks.execute_job(job_id) == {"status": "succeeded", "attempts": 2}
    failed_id = submit(context, "fail").json()["id"]
    monkeypatch.setattr(tasks, "export_workbook", render)
    for _ in range(tasks.MAX_ATTEMPTS):
        result = tasks.execute_job(failed_id)
    assert result["status"] == "failed"
    tasks.execute_job(failed_id)
    assert render.call_count == tasks.MAX_ATTEMPTS + 1


def test_worker_crash_rolls_back_export(context, monkeypatch):
    job_id = submit(context).json()["id"]
    original = tasks.export_workbook

    def crash(db, job):
        job.output = b"incomplete"
        db.flush()
        raise SystemExit("simulated process crash")

    monkeypatch.setattr(tasks, "export_workbook", crash)
    with pytest.raises(SystemExit):
        tasks.execute_job(job_id)
    with SessionLocal() as db:
        job = db.get(Job, UUID(job_id))
        assert job.status == "pending" and job.output is None and job.attempts == 0
    monkeypatch.setattr(tasks, "export_workbook", original)
    assert tasks.execute_job(job_id)["status"] == "succeeded"


def test_locked_delivery_retries_and_missing_job_is_ignored(context, monkeypatch):
    from uuid import uuid4

    assert tasks.execute_job(str(uuid4()))["status"] == "missing"
    monkeypatch.setattr(tasks, "execute_job", Mock(return_value={"status": "locked"}))
    with pytest.raises(Retry):
        tasks.run_job.run(str(uuid4()))


def test_export_limit_fails_without_partial_artifact(context, monkeypatch):
    job_id = submit(context).json()["id"]
    monkeypatch.setattr(tasks, "MAX_EXPORT_ROWS", 0)
    assert tasks.execute_job(job_id)["status"] == "failed"
    with SessionLocal() as db:
        job = db.get(Job, UUID(job_id))
        assert job.output is None and job.error_code == "ValueError"


def test_reminder_schedule_deduplicates_and_filters(context, monkeypatch):
    _, owner, stranger, project, _, _, publish = context
    monkeypatch.setattr(config, "EMAIL_ENABLED", True)
    send = Mock()
    monkeypatch.setattr(notifications, "send_email", send)
    tomorrow = datetime.combine(
        datetime.now(ZoneInfo(config.CELERY_TIMEZONE)).date() + timedelta(days=1),
        datetime.min.time(), ZoneInfo(config.CELERY_TIMEZONE),
    )
    with SessionLocal.begin() as db:
        db.add_all([
            Task(title="Done", project_id=project.id, assignee_id=stranger.id,
                 status=TaskStatus.DONE, due_date=utc_now() - timedelta(days=1)),
            Task(title="Tomorrow", project_id=project.id, assignee_id=stranger.id, due_date=tomorrow),
            Task(title="Unassigned", project_id=project.id, due_date=utc_now()),
        ])
    assert tasks.schedule_reminders.run() == 1
    assert tasks.schedule_reminders.run() == 1
    with SessionLocal() as db:
        reminders = db.scalars(select(Job).where(Job.kind == "reminder")).all()
        assert len(reminders) == 1
        job_id = str(reminders[0].id)
        assert reminders[0].owner_id == owner.id
    assert jobs.dispatch_pending() == 1
    assert publish.call_args.kwargs["queue"] == "maintenance"
    assert tasks.execute_job(job_id)["status"] == "succeeded"
    assert tasks.execute_job(job_id)["status"] == "succeeded"
    send.assert_called_once()
    assert send.call_args.args[0] == owner.email
    assert "Tomorrow" not in send.call_args.args[2]


@pytest.mark.parametrize("failure", ["timeout", "crash"])
def test_uncertain_smtp_never_automatically_resends(context, monkeypatch, failure):
    monkeypatch.setattr(config, "EMAIL_ENABLED", True)
    tasks.schedule_reminders.run()
    with SessionLocal() as db:
        job_id = str(db.scalar(select(Job.id).where(Job.kind == "reminder")))
    send = Mock(side_effect=TimeoutError() if failure == "timeout" else SystemExit())
    monkeypatch.setattr(notifications, "send_email", send)
    if failure == "crash":
        with pytest.raises(SystemExit):
            tasks.execute_job(job_id)
        assert tasks.execute_job(job_id)["status"] == "sending"
        with SessionLocal.begin() as db:
            db.get(Job, UUID(job_id)).updated_at = utc_now() - timedelta(minutes=11)
        jobs.dispatch_pending()
    else:
        assert tasks.execute_job(job_id)["status"] == "uncertain"
    assert tasks.execute_job(job_id)["status"] == "uncertain"
    send.assert_called_once()


def test_disabled_reminders_and_inactive_user(context, monkeypatch):
    assert tasks.schedule_reminders.run() == 0
    monkeypatch.setattr(config, "EMAIL_ENABLED", True)
    tasks.schedule_reminders.run()
    with SessionLocal.begin() as db:
        job = db.scalar(select(Job).where(Job.kind == "reminder"))
        db.get(User, job.owner_id).is_active = False
        job_id = str(job.id)
    send = Mock()
    monkeypatch.setattr(notifications, "send_email", send)
    assert tasks.execute_job(job_id)["status"] == "skipped"
    send.assert_not_called()


def test_beat_uses_local_eight_am():
    schedule = celery_app.conf.beat_schedule["daily-task-reminders"]["schedule"]
    assert schedule.hour == {8} and schedule.minute == {0}
    assert celery_app.conf.timezone == "Asia/Ho_Chi_Minh"
    assert celery_app.conf.task_acks_late and celery_app.conf.task_reject_on_worker_lost
    assert celery_app.conf.task_time_limit < celery_app.conf.visibility_timeout
