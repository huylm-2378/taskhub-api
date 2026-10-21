import logging
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import error_messages as errors
from celery_app import celery_app
from database import SessionLocal
from models import Job
from models.base import utc_now

logger = logging.getLogger(__name__)


class IdempotencyConflict(ValueError):
    pass


def create_job(db: Session, owner_id: UUID, kind: str, key: str, payload: dict) -> Job:
    """Caller commits; a unique constraint arbitrates concurrent submissions."""
    statement = select(Job).where(
        Job.owner_id == owner_id, Job.kind == kind, Job.idempotency_key == key,
    )
    job = db.scalar(statement)
    if job is None:
        try:
            with db.begin_nested():
                job = Job(owner_id=owner_id, kind=kind, idempotency_key=key, payload=payload)
                db.add(job)
                db.flush()
        except IntegrityError:
            job = db.scalar(statement)
            if job is None:
                raise
    if job.payload != payload:
        raise IdempotencyConflict(errors.IDEMPOTENCY_KEY_CONFLICT)
    return job


def dispatch_job(job_id: UUID) -> bool:
    """DB acts as an outbox. A publish/commit crash can duplicate, never lose, work."""
    with SessionLocal.begin() as db:
        job = db.scalar(select(Job).where(
            Job.id == job_id, Job.status == "pending", Job.available_at <= utc_now(),
        ).with_for_update(skip_locked=True))
        if job is None:
            return False
        celery_app.send_task(
            "taskhub.execute_job", args=[str(job.id)], task_id=str(job.id),
            queue="heavy" if job.kind == "export" else "maintenance",
            retry=False,
        )
        # Re-publish if delivery disappears. Workers serialize on this same row.
        job.available_at = utc_now() + timedelta(minutes=5)
    return True


def try_dispatch(job_id: UUID) -> None:
    try:
        dispatch_job(job_id)
    except Exception as exc:
        # Do not log broker URLs/passwords; the committed job remains recoverable.
        logger.warning("Job publish deferred: job_id=%s error=%s", job_id, type(exc).__name__)


def dispatch_pending() -> int:
    with SessionLocal.begin() as db:
        # SMTP may have succeeded before a process died. Never auto-resend.
        db.execute(update(Job).where(
            Job.status == "sending", Job.updated_at < utc_now() - timedelta(minutes=10),
        ).values(status="uncertain", error_code="delivery_unknown", updated_at=utc_now()))
        job_ids = db.scalars(select(Job.id).where(
            Job.status == "pending", Job.available_at <= utc_now(),
        ).order_by(Job.available_at, Job.id).limit(100)).all()
    count = 0
    for job_id in job_ids:
        if dispatch_job(job_id):
            count += 1
    return count
