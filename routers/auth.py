from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError

import error_messages as errors
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
        raise HTTPException(status_code=409, detail=errors.EMAIL_OR_USERNAME_EXISTS) from None


@router.post("/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DBSession, response: Response):
    user = users.get_by_username(db, form.username)
    if not verify_password(form.password, user.hashed_password if user else None):
        raise HTTPException(
            status_code=401, detail=errors.INCORRECT_USERNAME_OR_PASSWORD, headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail=errors.INACTIVE_USER)
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
        raise HTTPException(status_code=409, detail=errors.EMAIL_OR_USERNAME_EXISTS) from None
