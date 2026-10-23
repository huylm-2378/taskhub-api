from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from models import UserRole
from routers import projects
from schemas.project import ProjectCreate, ProjectUpdate


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("owner_state, status, detail", [
    ("missing", 404, "Owner not found"),
    ("inactive", 409, "Owner is inactive"),
])
def test_invalid_owner_prevents_project_write(monkeypatch, operation, owner_state, status, detail):
    owner_id = uuid4()
    owner = None if owner_state == "missing" else SimpleNamespace(is_active=False)
    monkeypatch.setattr(projects.users, "get", Mock(return_value=owner))
    write = Mock()
    monkeypatch.setattr(projects.projects, operation, write)
    db = Mock()

    with pytest.raises(HTTPException) as error:
        if operation == "create":
            projects.create_project(
                ProjectCreate(name="Rejected", owner_id=owner_id),
                db, SimpleNamespace(role=UserRole.ADMIN),
            )
        else:
            project = SimpleNamespace(id=uuid4(), name="Original", owner_id=uuid4())
            projects.update_project(
                project.id, ProjectUpdate(name="Rejected", owner_id=owner_id), db, project,
            )

    assert error.value.status_code == status
    assert error.value.detail == detail
    write.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("operation", ["create", "update"])
def test_active_owner_allows_project_write(monkeypatch, operation):
    owner_id = uuid4()
    monkeypatch.setattr(projects.users, "get", Mock(return_value=SimpleNamespace(is_active=True)))
    write = Mock()
    monkeypatch.setattr(projects.projects, operation, write)
    db = Mock()

    if operation == "create":
        data = ProjectCreate(name="Allowed", owner_id=owner_id)
        result = projects.create_project(data, db, SimpleNamespace(role=UserRole.ADMIN))
        write.assert_called_once_with(db, data)
    else:
        project = SimpleNamespace(id=uuid4())
        data = ProjectUpdate(owner_id=owner_id)
        result = projects.update_project(project.id, data, db, project)
        write.assert_called_once_with(db, project, data)
    assert result is write.return_value


def test_project_update_without_owner_does_not_validate_existing_owner(monkeypatch):
    lookup = Mock(return_value=SimpleNamespace(is_active=False))
    monkeypatch.setattr(projects.users, "get", lookup)
    write = Mock()
    monkeypatch.setattr(projects.projects, "update", write)
    project = SimpleNamespace(id=uuid4(), owner_id=uuid4())
    data = ProjectUpdate(name="Renamed")
    db = Mock()

    projects.update_project(project.id, data, db, project)

    lookup.assert_not_called()
    write.assert_called_once_with(db, project, data)
