from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from crud.common import save
from crud.pagination import paginate
from models import User
from schemas.user import UserCreate, UserRegister, UserUpdate


def create(db: Session, data: UserCreate) -> User:
    return save(db, User(**data.model_dump()))


def register(db: Session, data: UserRegister, hashed_password: str) -> User:
    return save(db, User(**data.model_dump(exclude={"password"}), hashed_password=hashed_password))


def get_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username.strip().lower()))


def update(db: Session, user: User, data: UserUpdate) -> User:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    return save(db, user)


def get(db: Session, user_id: UUID) -> User | None:
    return db.get(User, user_id)


def list_users(db: Session, offset: int, limit: int):
    statement = select(User).order_by(User.created_at, User.id)
    return paginate(db, statement, offset, limit)
