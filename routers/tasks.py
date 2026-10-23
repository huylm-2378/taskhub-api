from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response
from sqlalchemy.exc import IntegrityError

import error_messages as errors
from crud import bookmarks, tasks, users
from models import TaskStatus
from models.task import TaskPriority
from routers.dependencies import ActiveUser, DBSession, verify_project_manager
from routers.pagination import TaskPaginationDep
from schemas.bookmark import BookmarkRead
from schemas.comment import CommentCreate, CommentRead, CommentUpdate
from schemas.pagination import Page
from schemas.task import TaskAssign, TaskCreate, TaskRead, TaskUpdate
from services import notifications, task_interactions

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


@router.post("", response_model=TaskRead, status_code=201)
def create_task(data: TaskCreate, db: DBSession, current_user: ActiveUser):
    verify_project_manager(data.project_id, current_user, db)
    if data.assignee_id is not None:
        assignee = users.get(db, data.assignee_id)
        if assignee is None:
            raise HTTPException(status_code=404, detail=errors.ASSIGNEE_NOT_FOUND)
        if not assignee.is_active:
            raise HTTPException(status_code=409, detail=errors.ASSIGNEE_INACTIVE)
    try:
        return tasks.create(db, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=errors.TASK_REFERENCES_CHANGED) from None


@router.get("", response_model=Page[TaskRead])
def list_tasks(
    db: DBSession,
    pagination: TaskPaginationDep,
    project_id: UUID | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assignee_id: UUID | None = None,
):
    items, total = tasks.list_tasks(
        db,
        offset=pagination.offset,
        limit=pagination.limit,
        project_id=project_id,
        status=status,
        priority=priority,
        assignee_id=assignee_id,
    )

    return Page[TaskRead](
        items=items,
        total=total,
        offset=pagination.offset,
        limit=pagination.limit,
    )


@router.post("/{task_id}/bookmark", response_model=BookmarkRead)
def bookmark_task(task_id: UUID, db: DBSession, current_user: ActiveUser):
    if tasks.get(db, task_id) is None:
        raise HTTPException(status_code=404, detail=errors.TASK_NOT_FOUND)
    try:
        return bookmarks.create(db, current_user.id, task_id)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=errors.BOOKMARK_REFERENCES_CHANGED) from None


@router.delete("/{task_id}/bookmark", status_code=204)
def unbookmark_task(
    task_id: UUID,
    db: DBSession,
    current_user: ActiveUser,
):
    if tasks.get(db, task_id) is None:
        raise HTTPException(status_code=404, detail=errors.TASK_NOT_FOUND)

    bookmarks.delete(db, current_user.id, task_id)
    return Response(status_code=204)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: UUID, db: DBSession):
    task = tasks.get(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=errors.TASK_NOT_FOUND)
    return task


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(task_id: UUID, data: TaskUpdate, db: DBSession, current_user: ActiveUser):
    return task_interactions.update_task(db, task_id, data, current_user)


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: UUID, db: DBSession, current_user: ActiveUser):
    task_interactions.delete_task(db, task_id, current_user)
    return Response(status_code=204)


@router.post("/{task_id}/assign", response_model=TaskRead)
def assign_task(task_id: UUID, data: TaskAssign, db: DBSession, current_user: ActiveUser):
    return task_interactions.assign_task(db, task_id, data.assignee_id, current_user)


@router.post("/{task_id}/comments", response_model=CommentRead, status_code=201)
def add_comment(
    task_id: UUID,
    data: CommentCreate,
    background_tasks: BackgroundTasks,
    db: DBSession,
    current_user: ActiveUser,
):
    comment = task_interactions.add_comment(db, task_id, data.content, current_user)
    background_tasks.add_task(notifications.notify_comment, comment.id)
    return comment


@router.patch("/{task_id}/comments/{comment_id}", response_model=CommentRead)
def edit_comment(
    task_id: UUID,
    comment_id: UUID,
    data: CommentUpdate,
    db: DBSession,
    current_user: ActiveUser,
):
    return task_interactions.edit_comment(db, task_id, comment_id, data.content, current_user)


@router.delete("/{task_id}/comments/{comment_id}", status_code=204)
def delete_comment(task_id: UUID, comment_id: UUID, db: DBSession, current_user: ActiveUser):
    task_interactions.delete_comment(db, task_id, comment_id, current_user)
    return Response(status_code=204)
