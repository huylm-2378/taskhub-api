from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

import error_messages as errors
from models import Comment, Project, Task, TaskStatus, User, UserRole
from schemas.task import TaskUpdate
from services.transactions import transaction


def _task_context(db: Session, task_id: UUID) -> tuple[Task, Project]:
    # PostgreSQL holds both rows until commit/rollback, serializing mutations
    # with task deletion, assignment and project ownership transfers.
    row = db.execute(
        select(Task, Project).join(Project, Task.project_id == Project.id)
        .where(Task.id == task_id).with_for_update(of=(Task, Project))
        .execution_options(populate_existing=True)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=errors.TASK_NOT_FOUND)
    return row[0], row[1]


def _is_manager(user: User, project: Project) -> bool:
    return user.role == UserRole.ADMIN or project.owner_id == user.id


def _editable_comment(db: Session, task_id: UUID, comment_id: UUID, user: User) -> Comment:
    _, project = _task_context(db, task_id)
    comment = db.scalar(
        select(Comment).where(Comment.id == comment_id, Comment.task_id == task_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if comment is None:
        raise HTTPException(status_code=404, detail=errors.COMMENT_NOT_FOUND)
    if comment.author_id != user.id and not _is_manager(user, project):
        raise HTTPException(status_code=403, detail=errors.COMMENT_AUTHOR_OR_PROJECT_MANAGER_REQUIRED)
    return comment


def assign_task(db: Session, task_id: UUID, assignee_id: UUID, user: User) -> Task:
    with transaction(db):
        task, project = _task_context(db, task_id)
        if not _is_manager(user, project):
            raise HTTPException(status_code=403, detail=errors.PROJECT_MANAGER_REQUIRED)
        assignee = db.scalar(
            select(User).where(User.id == assignee_id).with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if assignee is None:
            raise HTTPException(status_code=404, detail=errors.ASSIGNEE_NOT_FOUND)
        if not assignee.is_active:
            raise HTTPException(status_code=409, detail=errors.ASSIGNEE_INACTIVE)
        task.assignee_id = assignee.id
    return task


def update_task(db: Session, task_id: UUID, data: TaskUpdate, user: User) -> Task:
    changes = data.model_dump(exclude_unset=True)
    with transaction(db):
        task, project = _task_context(db, task_id)
        if not _is_manager(user, project):
            if task.assignee_id != user.id or set(changes) != {"status"}:
                raise HTTPException(status_code=403, detail=errors.PROJECT_MANAGER_EDIT_REQUIRED)
        target = changes.get("status", task.status)
        next_status = {TaskStatus.TODO: TaskStatus.IN_PROGRESS, TaskStatus.IN_PROGRESS: TaskStatus.DONE}
        if target != task.status and next_status.get(task.status) != target:
            raise HTTPException(status_code=409, detail=errors.INVALID_TASK_STATUS_TRANSITION)
        for field, value in changes.items():
            setattr(task, field, value)
    return task


def delete_task(db: Session, task_id: UUID, user: User) -> None:
    with transaction(db):
        task, project = _task_context(db, task_id)
        if not _is_manager(user, project):
            raise HTTPException(status_code=403, detail=errors.PROJECT_MANAGER_REQUIRED)
        # DB foreign keys cascade comments, bookmarks and task_tags; tags survive.
        db.delete(task)


def add_comment(db: Session, task_id: UUID, content: str, user: User) -> Comment:
    with transaction(db):
        task, _ = _task_context(db, task_id)
        comment = Comment(task_id=task.id, author_id=user.id, content=content)
        db.add(comment)
    return comment


def edit_comment(db: Session, task_id: UUID, comment_id: UUID, content: str, user: User) -> Comment:
    with transaction(db):
        comment = _editable_comment(db, task_id, comment_id, user)
        comment.content = content
    return comment


def delete_comment(db: Session, task_id: UUID, comment_id: UUID, user: User) -> None:
    with transaction(db):
        comment = _editable_comment(db, task_id, comment_id, user)
        db.delete(comment)
