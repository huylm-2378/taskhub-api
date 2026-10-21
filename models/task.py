from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.base import EntityMixin

if TYPE_CHECKING:
    from models.comment import Comment
    from models.project import Project
    from models.tag import Tag
    from models.user import User


class TaskStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"


class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def values(self) -> tuple[int, ...]:
        return {self.LOW: (1, 2), self.MEDIUM: (3,), self.HIGH: (4, 5)}[self]


class Task(EntityMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("priority BETWEEN 1 AND 5", name="priority_range"),
    )

    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(
            TaskStatus, native_enum=False, create_constraint=True, name="task_status"
        ),
        default=TaskStatus.TODO,
    )
    priority: Mapped[int] = mapped_column(default=3)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    assignee_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    project: Mapped["Project"] = relationship(back_populates="tasks")
    assignee: Mapped["User | None"] = relationship(back_populates="assigned_tasks")
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", passive_deletes=True
    )
    tags: Mapped[list["Tag"]] = relationship(
        secondary="task_tags", back_populates="tasks", order_by="(Tag.name, Tag.id)"
    )
