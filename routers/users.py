from uuid import UUID

from fastapi import APIRouter, HTTPException, Path
from sqlalchemy.exc import IntegrityError

import error_messages as errors
from crud import users
from routers.dependencies import AdminUser, DBSession
from routers.pagination import PaginationDep
from schemas.user import UserCreate, UserRead, UserSummary

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.post("", response_model=UserRead, status_code=201)
def create_user(data: UserCreate, db: DBSession, current_user: AdminUser):
    try:
        return users.create(db, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=errors.EMAIL_OR_USERNAME_EXISTS) from None


@router.get("", response_model=list[UserRead])
def list_users(
    db: DBSession,
    current_user: AdminUser,
    pagination: PaginationDep,
):
    return users.list_users(
        db,
        pagination.offset,
        pagination.limit,
    )


@router.get("/{user_id}", response_model=UserSummary)
def get_user(user_id: UUID, db: DBSession):
    user = users.get(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=errors.USER_NOT_FOUND)
    return user


@router.get("/{username}/profile", response_model=UserSummary)
def get_user_profile(
    db: DBSession,
    username: str = Path(
        min_length=3,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_]+$",
    ),
):
    user = users.get_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail=errors.USER_NOT_FOUND)
    return user
