from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, raiseload

from crud.common import save
from models import Tag, Task, TaskStatus
from models.task import TaskPriority
from schemas.task import ProjectTaskCreate, TaskCreate


def task_relationship_options():
    # Load response relationships up front; fail if serialization tries a lazy load.
    return joinedload(Task.assignee), joinedload(Task.tags), raiseload("*")


def create(db: Session, data: TaskCreate) -> Task:
    return save(db, Task(**data.model_dump()))


def create_in_project(db: Session, project_id: UUID, data: ProjectTaskCreate, tags: list[Tag]) -> Task:
    task = Task(**data.model_dump(exclude={"tag_ids"}), project_id=project_id, tags=tags)
    save(db, task)
    return db.scalars(
        select(Task).where(Task.id == task.id).options(*task_relationship_options())
    ).unique().one()


def list_for_project(
    db: Session, project_id: UUID, offset: int, limit: int, status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
):
    statement = (
        select(Task).where(Task.project_id == project_id)
        .options(*task_relationship_options()).order_by(Task.created_at, Task.id)
    )
    if status is not None:
        statement = statement.where(Task.status == status)
    if priority is not None:
        statement = statement.where(Task.priority.in_(priority.values))
    # A task can produce several JOIN rows (one per tag).
    return db.scalars(statement.offset(offset).limit(limit)).unique().all()


def get(db: Session, task_id: UUID) -> Task | None:
    return db.get(Task, task_id)


def list_tasks(
    db: Session, offset: int, limit: int,
    project_id: UUID | None = None, status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
):
    statement = select(Task).order_by(Task.created_at, Task.id)
    if project_id is not None:
        statement = statement.where(Task.project_id == project_id)
    if status is not None:
        statement = statement.where(Task.status == status)
    if priority is not None:
        statement = statement.where(Task.priority.in_(priority.values))
    return db.scalars(statement.offset(offset).limit(limit)).all()
