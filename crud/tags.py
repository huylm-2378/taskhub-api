from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from crud.common import save
from crud.pagination import paginate
from models import Tag
from schemas.tag import TagCreate, TagUpdate


def create(db: Session, data: TagCreate) -> Tag:
    return save(db, Tag(**data.model_dump()))


def get(db: Session, tag_id: UUID) -> Tag | None:
    return db.get(Tag, tag_id)


def get_many(db: Session, tag_ids: list[UUID]) -> list[Tag]:
    if not tag_ids:
        return []
    return list(db.scalars(select(Tag).where(Tag.id.in_(tag_ids))).all())


def update(db: Session, tag: Tag, data: TagUpdate) -> Tag:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(tag, field, value)
    return save(db, tag)


def list_tags(db: Session, offset: int, limit: int):
    statement = select(Tag).order_by(Tag.created_at, Tag.id)
    return paginate(db, statement, offset, limit)
