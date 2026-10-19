from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from crud import projects, tags, tasks, users
from models import TaskStatus, UserRole
from models.task import TaskPriority
from routers.dependencies import ActiveUser, DBSession, ManagedProject
from routers.pagination import resolve_skip
from schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from schemas.task import ProjectTaskCreate, TaskWithRelations

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(data: ProjectCreate, db: DBSession, current_user: ActiveUser):
    if current_user.role != UserRole.ADMIN and data.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot create a project for another user")
    if users.get(db, data.owner_id) is None:
        raise HTTPException(status_code=404, detail="Owner not found")
    try:
        return projects.create(db, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Project references changed; retry the request") from None


@router.get("", response_model=list[ProjectRead])
def list_projects(db: DBSession, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    return projects.list_projects(db, offset, limit)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(project_id: UUID, data: ProjectUpdate, db: DBSession, project: ManagedProject):
    if data.owner_id is not None and users.get(db, data.owner_id) is None:
        raise HTTPException(status_code=404, detail="Owner not found")
    try:
        return projects.update(db, project, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Project references changed; retry the request") from None


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: UUID, db: DBSession):
    project = projects.get(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/tasks", response_model=list[TaskWithRelations])
def list_project_tasks(
    project_id: UUID, db: DBSession,
    skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    offset: int | None = Query(None, ge=0, deprecated=True),
):
    if projects.get(db, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return tasks.list_for_project(db, project_id, resolve_skip(skip, offset), limit, status, priority)


@router.post("/{project_id}/tasks", response_model=TaskWithRelations, status_code=201)
def create_project_task(project_id: UUID, data: ProjectTaskCreate, db: DBSession, project: ManagedProject):
    if data.assignee_id is not None and users.get(db, data.assignee_id) is None:
        raise HTTPException(status_code=404, detail="Assignee not found")
    task_tags = tags.get_many(db, data.tag_ids)
    if len(task_tags) != len(data.tag_ids):
        raise HTTPException(status_code=404, detail="Tag not found")
    try:
        return tasks.create_in_project(db, project_id, data, task_tags)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Task references changed; retry the request") from None
