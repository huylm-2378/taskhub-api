from typing import Generic, TypeVar

from pydantic import BaseModel, Field

Item = TypeVar("Item")


class Page(BaseModel, Generic[Item]):
    items: list[Item]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
