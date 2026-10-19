from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from crud.common import save
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


def list_projects(db: Session, offset: int, limit: int):
    return db.scalars(select(Project).order_by(Project.created_at, Project.id).offset(offset).limit(limit)).all()
