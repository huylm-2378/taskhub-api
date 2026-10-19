from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from database import get_db
from models import Project, User, UserRole
from security import decode_access_token

DBSession = Annotated[Session, Depends(get_db)]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/users/login")


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DBSession) -> User:
    error = HTTPException(
        status_code=401, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = decode_access_token(token)
    except (InvalidTokenError, ValueError, TypeError, AttributeError):
        raise error from None
    user = db.get(User, user_id)
    if user is None or user.hashed_password is None:
        raise error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_user(current_user: CurrentUser) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    return current_user


ActiveUser = Annotated[User, Depends(get_current_active_user)]


def verify_admin_role(current_user: ActiveUser) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user


AdminUser = Annotated[User, Depends(verify_admin_role)]


def verify_project_manager(project_id: UUID, current_user: ActiveUser, db: DBSession) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if current_user.role != UserRole.ADMIN and project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Project manager permission required")
    return project


ManagedProject = Annotated[Project, Depends(verify_project_manager)]
