from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from models import Comment, Project, Tag, Task, User, task_tags


def test_relationships_and_cascade(client):
    with SessionLocal() as db:
        owner = User(name="Huy", email="huy@example.com")
        project = Project(name="TaskHub", owner=owner)
        task = Task(title="Build", project=project, assignee=owner)
        comment = Comment(content="Ready", task=task, author=owner)
        tag = Tag(name="backend")
        task.tags.append(tag)
        db.add_all([owner, project, task, comment])
        db.commit()
        task_id = task.id
        db.expire_all()
        stored = db.get(Task, task_id)
        assert stored.project.owner.email == "huy@example.com"
        assert stored.comments[0].author.id == owner.id
        assert stored.tags[0].name == "backend"
        db.execute(delete(Project).where(Project.id == project.id))
        db.commit()
        for model in [Task, Comment, task_tags]:
            assert db.scalar(select(func.count()).select_from(model)) == 0
        assert db.scalar(select(func.count()).select_from(Tag)) == 1


def test_database_rejects_missing_owner(client):
    with SessionLocal() as db:
        db.add(Project(name="Orphan", owner_id=uuid4()))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
