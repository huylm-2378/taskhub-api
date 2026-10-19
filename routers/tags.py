from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from crud import tags
from routers.dependencies import DBSession
from schemas.tag import TagCreate, TagRead, TagUpdate
from services import tag_cache

router = APIRouter(prefix="/api/tags", tags=["Tags"])


@router.post("", response_model=TagRead, status_code=201)
def create_tag(data: TagCreate, db: DBSession):
    try:
        tag = tags.create(db, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Tag name already exists") from None
    tag_cache.invalidate()
    return tag


@router.patch("/{tag_id}", response_model=TagRead)
def update_tag(tag_id: UUID, data: TagUpdate, db: DBSession):
    tag = tags.get(db, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    try:
        tag = tags.update(db, tag, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Tag name already exists") from None
    tag_cache.invalidate()
    return tag


@router.get("", response_model=list[TagRead])
def list_tags(db: DBSession, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    return tag_cache.list_tags(db, offset, limit)
