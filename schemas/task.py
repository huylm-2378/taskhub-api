from datetime import UTC, datetime
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator

import error_messages as errors
from models.task import TaskStatus
from schemas.base import InputSchema, ReadSchema
from schemas.tag import TagRead
from schemas.user import UserSummary


class TaskFields(InputSchema):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    priority: int = Field(default=3, ge=1, le=5)
    due_date: AwareDatetime | None = None
    assignee_id: UUID | None = None

    @field_validator("due_date")
    @classmethod
    def normalize_due_date(cls, value: datetime | None) -> datetime | None:
        value = normalize_utc(value)

        if value is not None and value < datetime.now(UTC):
            raise ValueError(errors.DUE_DATE_IN_PAST)

        return value


class TaskCreate(TaskFields):
    project_id: UUID


class TaskAssign(InputSchema):
    assignee_id: UUID


class TaskUpdate(InputSchema):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    status: TaskStatus | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    due_date: AwareDatetime | None = None

    @field_validator("title", "status", "priority")
    @classmethod
    def reject_null_required_fields(cls, value):
        if value is None:
            raise ValueError(errors.FIELD_CANNOT_BE_NULL)
        return value

    @field_validator("due_date")
    @classmethod
    def normalize_due_date(cls, value: datetime | None) -> datetime | None:
        return normalize_utc(value)


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
    assignee: UserSummary | None
    tags: list[TagRead]


def normalize_utc(value: datetime | None) -> datetime | None:
    """Convert a timezone-aware datetime to UTC, preserving None."""
    if value is None:
        return None
    return value.astimezone(UTC)
