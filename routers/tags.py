from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

import error_messages as errors
from crud import tags
from routers.dependencies import AdminUser, DBSession
from routers.pagination import PaginationDep
from schemas.pagination import Page
from schemas.tag import TagCreate, TagRead, TagUpdate
from services import tag_cache

router = APIRouter(prefix="/api/tags", tags=["Tags"])


@router.post("", response_model=TagRead, status_code=201)
def create_tag(data: TagCreate, db: DBSession, current_user: AdminUser):
    try:
        tag = tags.create(db, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=errors.TAG_NAME_EXISTS) from None
    tag_cache.invalidate()
    return tag


@router.patch("/{tag_id}", response_model=TagRead)
def update_tag(tag_id: UUID, data: TagUpdate, db: DBSession, current_user: AdminUser):
    tag = tags.get(db, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail=errors.TAG_NOT_FOUND)
    try:
        tag = tags.update(db, tag, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=errors.TAG_NAME_EXISTS) from None
    tag_cache.invalidate()
    return tag


@router.get("", response_model=Page[TagRead])
def list_tags(db: DBSession, pagination: PaginationDep):
    return tag_cache.list_tags(db, pagination.offset, pagination.limit)
