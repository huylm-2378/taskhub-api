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
    db.execute.return_value.rowcount = 1
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


@pytest.mark.parametrize("rowcount, expected", [(0, False), (1, True)])
def test_delete_bookmark_reports_whether_a_row_was_deleted(rowcount, expected):
    db = Mock()
    db.execute.return_value.rowcount = rowcount

    assert bookmarks.delete(db, uuid4(), uuid4()) is expected

    db.commit.assert_called_once_with()
    db.rollback.assert_not_called()


@pytest.mark.parametrize("deleted", [False, True])
def test_unbookmark_response_depends_on_current_users_bookmark(monkeypatch, deleted):
    db = Mock()
    task_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(tasks.tasks, "get", Mock(return_value=SimpleNamespace(id=task_id)))
    delete_bookmark = Mock(return_value=deleted)
    monkeypatch.setattr(tasks.bookmarks, "delete", delete_bookmark)

    if deleted:
        response = tasks.unbookmark_task(task_id, db, user)
        assert response.status_code == 204
        assert response.body == b""
    else:
        with pytest.raises(HTTPException) as caught:
            tasks.unbookmark_task(task_id, db, user)
        assert caught.value.status_code == 404
        assert caught.value.detail == "Bookmark not found"

    delete_bookmark.assert_called_once_with(db, user.id, task_id)
