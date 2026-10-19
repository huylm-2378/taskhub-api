from datetime import UTC, datetime
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator

from models.task import TaskStatus
from schemas.base import InputSchema, ReadSchema
from schemas.tag import TagRead
from schemas.user import UserRead


class TaskFields(InputSchema):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    status: TaskStatus = TaskStatus.TODO
    priority: int = Field(default=3, ge=1, le=5)
    due_date: AwareDatetime | None = None
    assignee_id: UUID | None = None

    @field_validator("due_date")
    @classmethod
    def normalize_due_date(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value else None


class TaskCreate(TaskFields):
    project_id: UUID


class TaskAssign(InputSchema):
    assignee_id: UUID


class ProjectTaskCreate(TaskFields):
    tag_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @field_validator("tag_ids")
    @classmethod
    def unique_tag_ids(cls, value: list[UUID]) -> list[UUID]:
        return list(dict.fromkeys(value))


class TaskRead(ReadSchema):
    title: str
    description: str | None
    status: TaskStatus
    priority: int
    due_date: datetime | None
    project_id: UUID
    assignee_id: UUID | None


class TaskWithRelations(TaskRead):
    assignee: UserRead | None
    tags: list[TagRead]
