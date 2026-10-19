from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from crud.common import save
from models import Bookmark


def create(db: Session, user_id: UUID, task_id: UUID) -> Bookmark:
    existing = db.get(Bookmark, (user_id, task_id))
    if existing is not None:
        return existing
    try:
        return save(db, Bookmark(user_id=user_id, task_id=task_id))
    except IntegrityError:
        # The composite primary key also handles concurrent duplicate requests.
        existing = db.get(Bookmark, (user_id, task_id))
        if existing is None:
            raise
        return existing
