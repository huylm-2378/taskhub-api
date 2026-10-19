from typing import TypeVar

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import Base

Entity = TypeVar("Entity", bound=Base)


def save(db: Session, entity: Entity) -> Entity:
    db.add(entity)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(entity)
    return entity
