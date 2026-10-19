from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError

from crud import users
from routers.dependencies import ActiveUser, DBSession
from schemas.auth import Token
from schemas.user import UserRead, UserRegister, UserUpdate
from security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/users", tags=["Authentication"])


@router.post("/register", response_model=UserRead, status_code=201)
def register(data: UserRegister, db: DBSession):
    hashed_password = hash_password(data.password.get_secret_value())
    try:
        return users.register(db, data, hashed_password)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Email or username already exists") from None


@router.post("/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DBSession, response: Response):
    user = users.get_by_username(db, form.username)
    if not verify_password(form.password, user.hashed_password if user else None):
        raise HTTPException(
            status_code=401, detail="Incorrect username or password", headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserRead)
def get_me(current_user: ActiveUser):
    return current_user


@router.put("/me", response_model=UserRead)
def update_me(data: UserUpdate, current_user: ActiveUser, db: DBSession):
    try:
        return users.update(db, current_user, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Email or username already exists") from None
