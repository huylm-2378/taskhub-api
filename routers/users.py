from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy.exc import IntegrityError

from crud import users
from routers.dependencies import AdminUser, DBSession
from schemas.user import UserCreate, UserRead
from schemas.profile import UserProfile

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.post("", response_model=UserRead, status_code=201)
def create_user(data: UserCreate, db: DBSession, current_user: AdminUser):
    try:
        return users.create(db, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Email or username already exists") from None


@router.get("", response_model=list[UserRead])
def list_users(db: DBSession, current_user: AdminUser, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    return users.list_users(db, offset, limit)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: UUID, db: DBSession):
    user = users.get(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/{username}/profile", response_model=UserProfile)
def get_user_profile(
    db: DBSession,
    username: str = Path(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_]+$"),
):
    user = users.get_profile(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user
