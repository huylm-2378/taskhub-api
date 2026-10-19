from uuid import UUID

from pydantic import Field

from schemas.base import InputSchema, ReadSchema


class CommentCreate(InputSchema):
    content: str = Field(min_length=1, max_length=10000)


class CommentUpdate(InputSchema):
    content: str = Field(min_length=1, max_length=10000)


class CommentRead(ReadSchema):
    content: str
    task_id: UUID
    author_id: UUID
