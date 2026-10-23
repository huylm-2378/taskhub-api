from enum import Enum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, String, true
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.base import EntityMixin

if TYPE_CHECKING:
    from models.comment import Comment
    from models.project import Project
    from models.task import Task


class UserRole(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class User(EntityMixin, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, native_enum=False, create_constraint=True, name="user_role"),
        default=UserRole.USER,
        server_default="USER",
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=lambda: f"user_{uuid4().hex}")

    projects: Mapped[list["Project"]] = relationship(
        back_populates="owner", order_by="(Project.created_at, Project.id)"
    )
    assigned_tasks: Mapped[list["Task"]] = relationship(
        back_populates="assignee", order_by="(Task.created_at, Task.id)"
    )
    comments: Mapped[list["Comment"]] = relationship(back_populates="author")
