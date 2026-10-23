from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.base import EntityMixin

if TYPE_CHECKING:
    from models.task import Task

task_tags = Table(
    "task_tags",
    Base.metadata,
    Column("task_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(EntityMixin, Base):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(50), unique=True)
    tasks: Mapped[list["Task"]] = relationship(secondary=task_tags, back_populates="tags")
