from datetime import datetime, timezone
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, inspect, text

import config


def test_username_migration_preserves_existing_relations(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    monkeypatch.setattr(config, "DATABASE_URL", url)
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "770764801816")
    legacy_engine = create_engine(url)
    try:
        metadata = MetaData()
        metadata.reflect(legacy_engine)
        owner_id, other_id, project_id, task_id, tag_id = [uuid4().hex for _ in range(5)]
        now = datetime.now(timezone.utc)
        with legacy_engine.begin() as connection:
            connection.execute(metadata.tables["users"].insert(), [
                {"id": owner_id, "name": "Same name", "email": "first@example.com", "created_at": now},
                {"id": other_id, "name": "Same name", "email": "second@example.com", "created_at": now},
            ])
            connection.execute(metadata.tables["projects"].insert(), {
                "id": project_id, "name": "Existing project", "owner_id": owner_id, "created_at": now,
            })
            connection.execute(metadata.tables["tasks"].insert(), {
                "id": task_id, "title": "Existing task", "project_id": project_id,
                "assignee_id": other_id, "status": "TODO", "priority": 3, "created_at": now,
            })
            connection.execute(metadata.tables["tags"].insert(), {
                "id": tag_id, "name": "existing", "created_at": now,
            })
            connection.execute(metadata.tables["task_tags"].insert(), {"task_id": task_id, "tag_id": tag_id})

        command.upgrade(cfg, "head")
        command.check(cfg)
        with legacy_engine.connect() as connection:
            users = dict(connection.execute(text("SELECT id, username FROM users")).all())
            assert users == {owner_id: f"user_{owner_id}", other_id: f"user_{other_id}"}
            assert connection.execute(text("SELECT hashed_password FROM users")).scalars().all() == [None, None]
            assert connection.execute(text("SELECT role, is_active FROM users")).all() == [
                ("USER", True), ("USER", True),
            ]
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
            assert connection.execute(text(
                "SELECT p.owner_id, t.assignee_id, tt.tag_id FROM projects p "
                "JOIN tasks t ON t.project_id = p.id JOIN task_tags tt ON tt.task_id = t.id"
            )).one() == (owner_id, other_id, tag_id)
        username_column = next(column for column in inspect(legacy_engine).get_columns("users") if column["name"] == "username")
        assert username_column["nullable"] is False

        command.downgrade(cfg, "770764801816")
        assert "username" not in {column["name"] for column in inspect(legacy_engine).get_columns("users")}
        command.upgrade(cfg, "head")
        with legacy_engine.connect() as connection:
            assert dict(connection.execute(text("SELECT id, username FROM users")).all()) == users
            assert connection.execute(text("SELECT count(*) FROM task_tags")).scalar_one() == 1
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        legacy_engine.dispose()
