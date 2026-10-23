from uuid import UUID

from pydantic import Field, field_validator

import error_messages as errors
from schemas.base import InputSchema, ReadSchema


class ProjectCreate(InputSchema):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    owner_id: UUID


class ProjectUpdate(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    owner_id: UUID | None = None

    @field_validator("name", "owner_id")
    @classmethod
    def reject_null_required_fields(cls, value):
        if value is None:
            raise ValueError(errors.FIELD_CANNOT_BE_NULL)
        return value


class ProjectRead(ReadSchema):
    name: str
    description: str | None
    owner_id: UUID
