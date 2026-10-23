from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

import error_messages as errors
from crud import projects, tags, tasks, users
from models import TaskStatus, UserRole
from models.task import TaskPriority
from routers.dependencies import ActiveUser, DBSession, ManagedProject
from routers.pagination import PaginationDep, TaskPaginationDep
from schemas.pagination import Page
from schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from schemas.task import ProjectTaskCreate, TaskWithRelations

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(data: ProjectCreate, db: DBSession, current_user: ActiveUser):
    if current_user.role != UserRole.ADMIN and data.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail=errors.CANNOT_CREATE_PROJECT_FOR_ANOTHER_USER)
    _validate_owner(db, data.owner_id)
    try:
        return projects.create(db, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=errors.PROJECT_REFERENCES_CHANGED) from None


@router.get("", response_model=Page[ProjectRead])
def list_projects(
    db: DBSession,
    pagination: PaginationDep,
    owner_id: UUID | None = None,
):
    items, total = projects.list_projects(
        db,
        offset=pagination.offset,
        limit=pagination.limit,
        owner_id=owner_id,
    )

    return Page[ProjectRead](
        items=items,
        total=total,
        offset=pagination.offset,
        limit=pagination.limit,
    )


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(project_id: UUID, data: ProjectUpdate, db: DBSession, project: ManagedProject):
    if data.owner_id is not None:
        _validate_owner(db, data.owner_id)
    try:
        return projects.update(db, project, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=errors.PROJECT_REFERENCES_CHANGED) from None


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: UUID, db: DBSession):
    project = projects.get(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=errors.PROJECT_NOT_FOUND)
    return project


@router.get(
    "/{project_id}/tasks",
    response_model=Page[TaskWithRelations],
)
def list_project_tasks(
    project_id: UUID,
    db: DBSession,
    pagination: TaskPaginationDep,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
):
    if projects.get(db, project_id) is None:
        raise HTTPException(status_code=404, detail=errors.PROJECT_NOT_FOUND)

    items, total = tasks.list_for_project(
        db,
        project_id=project_id,
        offset=pagination.offset,
        limit=pagination.limit,
        status=status,
        priority=priority,
    )

    return Page[TaskWithRelations](
        items=items,
        total=total,
        offset=pagination.offset,
        limit=pagination.limit,
    )


@router.post("/{project_id}/tasks", response_model=TaskWithRelations, status_code=201)
def create_project_task(project_id: UUID, data: ProjectTaskCreate, db: DBSession, project: ManagedProject):
    if data.assignee_id is not None:
        assignee = users.get(db, data.assignee_id)
        if assignee is None:
            raise HTTPException(status_code=404, detail=errors.ASSIGNEE_NOT_FOUND)
        if not assignee.is_active:
            raise HTTPException(status_code=409, detail=errors.ASSIGNEE_INACTIVE)
    task_tags = tags.get_many(db, data.tag_ids)
    if len(task_tags) != len(data.tag_ids):
        raise HTTPException(status_code=404, detail=errors.TAG_NOT_FOUND)
    try:
        return tasks.create_in_project(db, project_id, data, task_tags)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=errors.TASK_REFERENCES_CHANGED) from None


def _validate_owner(db: DBSession, owner_id: UUID) -> None:
    owner = users.get(db, owner_id)

    if owner is None:
        raise HTTPException(status_code=404, detail=errors.OWNER_NOT_FOUND)

    if not owner.is_active:
        raise HTTPException(status_code=409, detail=errors.OWNER_INACTIVE)
