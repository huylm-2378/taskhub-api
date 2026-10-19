from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BookmarkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    task_id: UUID
    created_at: datetime
