from fastapi import HTTPException


def resolve_skip(skip: int, offset: int | None) -> int:
    if offset is not None:
        if skip != 0 and skip != offset:
            raise HTTPException(status_code=422, detail="skip and offset must match when both are provided")
        return offset
    return skip
