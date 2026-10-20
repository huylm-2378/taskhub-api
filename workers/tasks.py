from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from uuid import UUID
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

import config
from celery_app import celery_app
from database import SessionLocal
from models import Job, Project, Task, TaskStatus, User, UserRole
from models.base import utc_now
from services import jobs, notifications

MAX_ATTEMPTS = 5
MAX_EXPORT_ROWS = 100_000


def export_workbook(db, job: Job) -> bytes:
    owner = db.get(User, job.owner_id)
    project = db.get(Project, UUID(job.payload["project_id"]))
    if owner is None or not owner.is_active or project is None or (
        owner.role != UserRole.ADMIN and project.owner_id != owner.id
    ):
        raise PermissionError("Export permission no longer available")
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Tasks")
    sheet.append(["ID", "Title", "Status", "Priority", "Due date (UTC)", "Assignee ID"])
    statement = select(Task).where(Task.project_id == project.id).order_by(Task.id).limit(MAX_EXPORT_ROWS + 1)
    try:
        for index, task in enumerate(db.scalars(statement).yield_per(500)):
            if index >= MAX_EXPORT_ROWS:
                raise ValueError("Export row limit exceeded")
            values = [
                str(task.id), task.title, task.status.value, task.priority,
                task.due_date.isoformat() if task.due_date else "",
                str(task.assignee_id) if task.assignee_id else "",
            ]
            cells = []
            for value in values:
                cell = WriteOnlyCell(sheet, value=value)
                if isinstance(value, str):
                    cell.data_type = "s"  # Never interpret user text as an Excel formula.
                cells.append(cell)
            sheet.append(cells)
        with BytesIO() as output:
            workbook.save(output)
            return output.getvalue()
    finally:
        if not sheet.closed:
            sheet.close()
        workbook.close()


def reminder_message(db, job: Job):
    owner = db.get(User, job.owner_id)
    if not config.EMAIL_ENABLED or owner is None or not owner.is_active:
        return None
    day = date.fromisoformat(job.payload["date"])
    cutoff = datetime.combine(day + timedelta(days=1), time.min, ZoneInfo(config.CELERY_TIMEZONE))
    tasks = db.scalars(select(Task).where(
        Task.assignee_id == owner.id, Task.status != TaskStatus.DONE,
        Task.due_date < cutoff.astimezone(timezone.utc),
    ).order_by(Task.due_date, Task.id).limit(100)).all()
    if not tasks:
        return None
    body = "\n".join(f"- {task.title} ({task.id})" for task in tasks)
    return owner.email, f"TaskHub: việc cần làm ngày {day.isoformat()}", (
        "Công việc đến hạn hôm nay hoặc quá hạn (tối đa 100):\n" + body
    )


def execute_job(job_id: str) -> dict:
    mail = None
    with SessionLocal.begin() as db:
        job = db.scalar(select(Job).where(Job.id == UUID(job_id)).with_for_update(skip_locked=True))
        if job is None:
            # A publisher can still hold the row while its message reaches us.
            return {"status": "locked" if db.get(Job, UUID(job_id)) is not None else "missing"}
        if job.status != "pending":
            return {"status": job.status}
        job.attempts += 1
        job.updated_at = utc_now()
        try:
            if job.kind == "export":
                job.output = export_workbook(db, job)
                job.status = "succeeded"
            else:
                mail = reminder_message(db, job)
                # Commit BEFORE external side effect. Redeliveries skip this claim.
                job.status = "sending" if mail else "skipped"
            job.error_code = None
        except SQLAlchemyError:
            raise  # A broken transaction must roll back before retrying.
        except Exception as exc:
            job.error_code = type(exc).__name__
            terminal = isinstance(exc, (PermissionError, ValueError)) or job.attempts >= MAX_ATTEMPTS
            job.status = "failed" if terminal else "pending"
            job.available_at = utc_now() + timedelta(seconds=min(30 * 2 ** job.attempts, 600))
        result = {"status": job.status, "attempts": job.attempts}
    if mail is not None:
        # SMTP has no idempotency API: a timeout/crash is ambiguous, not retryable.
        try:
            notifications.send_email(*mail)
            status, error_code = "succeeded", None
        except Exception:
            status, error_code = "uncertain", "delivery_unknown"
        with SessionLocal.begin() as db:
            job = db.get(Job, UUID(job_id), with_for_update=True)
            if job is not None:
                job.status, job.error_code, job.updated_at = status, error_code, utc_now()
        result["status"] = status
    return result


@celery_app.task(
    bind=True, name="taskhub.execute_job", max_retries=5,
    autoretry_for=(SQLAlchemyError,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True,
)
def run_job(self, job_id: str):
    result = execute_job(job_id)
    if result["status"] == "locked":
        # Don't ACK a fast delivery and leave it waiting for the outbox sweep.
        raise self.retry(countdown=5, max_retries=360)
    if result["status"] == "pending":
        raise self.retry(countdown=min(30 * 2 ** result["attempts"], 600))
    return result


@celery_app.task(name="taskhub.dispatch_pending")
def dispatch_pending():
    return jobs.dispatch_pending()


@celery_app.task(
    name="taskhub.schedule_reminders", autoretry_for=(SQLAlchemyError,),
    retry_backoff=True, max_retries=5,
)
def schedule_reminders():
    if not config.EMAIL_ENABLED:
        return 0
    day = datetime.now(ZoneInfo(config.CELERY_TIMEZONE)).date()
    cutoff = datetime.combine(day + timedelta(days=1), time.min, ZoneInfo(config.CELERY_TIMEZONE))
    with SessionLocal.begin() as db:
        owners = db.scalars(select(User.id).where(
            User.is_active.is_(True),
            select(Task.id).where(
                Task.assignee_id == User.id, Task.status != TaskStatus.DONE,
                Task.due_date < cutoff.astimezone(timezone.utc),
            ).exists(),
        )).all()
        for owner_id in owners:
            jobs.create_job(db, owner_id, "reminder", f"daily:{day.isoformat()}", {"date": day.isoformat()})
    # Beat's outbox sweep handles publishing even if this process dies here.
    return len(owners)
