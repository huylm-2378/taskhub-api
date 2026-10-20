from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from schemas.base import InputSchema, ReadSchema


class ExportCreate(InputSchema):
    project_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")


class JobRead(ReadSchema):
    kind: Literal["export", "reminder"]
    status: Literal["pending", "sending", "succeeded", "failed", "uncertain", "skipped"]
    attempts: int
    updated_at: datetime
    error_code: str | None
