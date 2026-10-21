from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from crud import bookmarks
from routers import tasks


@pytest.mark.parametrize("failed_operation", ["execute", "commit"])
def test_delete_bookmark_rolls_back_database_errors(failed_operation):
    db = Mock()
    error = SQLAlchemyError("Database write failed")
    getattr(db, failed_operation).side_effect = error

    with pytest.raises(SQLAlchemyError) as caught:
        bookmarks.delete(db, uuid4(), uuid4())

    assert caught.value is error
    db.rollback.assert_called_once_with()
    if failed_operation == "execute":
        db.commit.assert_not_called()


def test_unbookmark_missing_task_does_not_delete(monkeypatch):
    monkeypatch.setattr(tasks.tasks, "get", Mock(return_value=None))
    delete_bookmark = Mock()
    monkeypatch.setattr(tasks.bookmarks, "delete", delete_bookmark)

    with pytest.raises(HTTPException) as caught:
        tasks.unbookmark_task(uuid4(), Mock(), SimpleNamespace(id=uuid4()))

    assert caught.value.status_code == 404
    assert caught.value.detail == "Task not found"
    delete_bookmark.assert_not_called()
