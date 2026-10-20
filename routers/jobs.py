from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Job, User
from routers.dependencies import ActiveUser, DBSession, verify_project_manager
from schemas.job import ExportCreate, JobRead
from services import jobs

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.post("/exports", response_model=JobRead, status_code=202)
def create_export(data: ExportCreate, db: DBSession, current_user: ActiveUser):
    verify_project_manager(data.project_id, current_user, db)
    try:
        job = jobs.create_job(
            db, current_user.id, "export", data.idempotency_key,
            {"project_id": str(data.project_id)},
        )
        db.commit()
    except jobs.IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Job references changed; retry the request") from None
    jobs.try_dispatch(job.id)
    db.refresh(job)
    return job


def owned_job(job_id: UUID, db: Session, current_user: User) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.kind == "export":
        verify_project_manager(UUID(job.payload["project_id"]), current_user, db)
    return job


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: UUID, db: DBSession, current_user: ActiveUser):
    return owned_job(job_id, db, current_user)


@router.get("/{job_id}/download")
def download_export(job_id: UUID, db: DBSession, current_user: ActiveUser):
    job = owned_job(job_id, db, current_user)
    if job.kind != "export" or job.status != "succeeded":
        raise HTTPException(status_code=409, detail="Export is not ready")
    return Response(
        content=job.output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="tasks-{job.id}.xlsx"'},
    )
