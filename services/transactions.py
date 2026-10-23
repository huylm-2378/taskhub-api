from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

import error_messages as errors


@contextmanager
def transaction(db: Session) -> Iterator[None]:
    # Authentication already starts this request's transaction via SELECT.
    # Own its commit/rollback instead of starting a nested transaction or
    # calling CRUD helpers that commit before the business operation finishes.
    try:
        yield
        db.flush()
        db.commit()
    except (IntegrityError, StaleDataError):
        db.rollback()
        raise HTTPException(status_code=409, detail=errors.TASK_DATA_CHANGED) from None
    except Exception:
        db.rollback()
        raise
