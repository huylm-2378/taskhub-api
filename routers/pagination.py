from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Query

import error_messages as errors

DEFAULT_OFFSET = 0
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

OffsetQuery = Annotated[int, Query(ge=0)]
LimitQuery = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
LegacyOffsetQuery = Annotated[
    int | None,
    Query(ge=0, deprecated=True),
]


@dataclass(frozen=True)
class Pagination:
    offset: int
    limit: int


def resolve_skip(skip: int, offset: int | None) -> int:
    if offset is not None:
        if skip != 0 and skip != offset:
            raise HTTPException(
                status_code=422,
                detail=errors.PAGINATION_OFFSETS_MISMATCH,
            )
        return offset
    return skip


def get_pagination(
    offset: OffsetQuery = DEFAULT_OFFSET,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> Pagination:
    return Pagination(offset=offset, limit=limit)


def get_task_pagination(
    skip: OffsetQuery = DEFAULT_OFFSET,
    limit: LimitQuery = DEFAULT_LIMIT,
    offset: LegacyOffsetQuery = None,
) -> Pagination:
    return Pagination(
        offset=resolve_skip(skip, offset),
        limit=limit,
    )


PaginationDep = Annotated[Pagination, Depends(get_pagination)]
TaskPaginationDep = Annotated[Pagination, Depends(get_task_pagination)]
