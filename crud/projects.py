from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from crud.common import save
from crud.pagination import paginate
from models import Project
from schemas.project import ProjectCreate, ProjectUpdate


def create(db: Session, data: ProjectCreate) -> Project:
    return save(db, Project(**data.model_dump()))


def get(db: Session, project_id: UUID) -> Project | None:
    return db.get(Project, project_id)


def update(db: Session, project: Project, data: ProjectUpdate) -> Project:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    return save(db, project)


def list_projects(
    db: Session,
    offset: int,
    limit: int,
    owner_id: UUID | None = None,
):
    statement = select(Project)

    if owner_id is not None:
        statement = statement.where(Project.owner_id == owner_id)

    statement = statement.order_by(Project.created_at, Project.id)

    return paginate(db, statement, offset, limit)
