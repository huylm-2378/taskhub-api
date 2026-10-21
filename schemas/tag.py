from pydantic import Field, field_validator

import error_messages as errors
from schemas.base import InputSchema, ReadSchema


class TagCreate(InputSchema):
    name: str = Field(min_length=1, max_length=50)


class TagUpdate(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def reject_null_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError(errors.TAG_NAME_CANNOT_BE_NULL)
        return value


class TagRead(ReadSchema):
    name: str
