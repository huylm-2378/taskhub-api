from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InputSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ReadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
