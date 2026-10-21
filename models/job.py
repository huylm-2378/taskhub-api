from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.base import EntityMixin, utc_now


class Job(EntityMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("owner_id", "kind", "idempotency_key", name="uq_jobs_owner_kind_key"),
        CheckConstraint("kind IN ('export', 'reminder')", name="job_kind"),
        CheckConstraint(
            "status IN ('pending', 'sending', 'succeeded', 'failed', 'uncertain', 'skipped')",
            name="job_status",
        ),
        Index("ix_jobs_dispatch", "status", "available_at"),
    )

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    error_code: Mapped[str | None] = mapped_column(String(64))
    # Keep result + completion atomic. Large artifacts should use object storage.
    output: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
