from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Comment, Project, Task, User, UserRole
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
        raise HTTPException(status_code=404, detail="Task not found")
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
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.author_id != user.id and not _is_manager(user, project):
        raise HTTPException(status_code=403, detail="Comment author or project manager permission required")
    return comment


def assign_task(db: Session, task_id: UUID, assignee_id: UUID, user: User) -> Task:
    with transaction(db):
        task, project = _task_context(db, task_id)
        if not _is_manager(user, project):
            raise HTTPException(status_code=403, detail="Project manager permission required")
        assignee = db.scalar(
            select(User).where(User.id == assignee_id).with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if assignee is None:
            raise HTTPException(status_code=404, detail="Assignee not found")
        if not assignee.is_active:
            raise HTTPException(status_code=409, detail="Assignee is inactive")
        task.assignee_id = assignee.id
    return task


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
