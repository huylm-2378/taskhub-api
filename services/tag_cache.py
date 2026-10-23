import logging
from functools import lru_cache
from uuid import uuid4

from pydantic import ValidationError
from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry
from sqlalchemy.orm import Session

import config
from crud import tags
from schemas.pagination import Page
from schemas.tag import TagRead

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_client() -> Redis | None:
    if not config.REDIS_URL:
        return None
    try:
        return Redis.from_url(
            config.REDIS_URL,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
            retry=Retry(NoBackoff(), 0),
            decode_responses=True,
        )
    except (ValueError, RedisError):
        logger.warning("Invalid Redis configuration; tag caching disabled")
        return None


def close_cache() -> None:
    if get_client.cache_info().currsize:
        client = get_client()
        if client is not None:
            client.close()
    get_client.cache_clear()


def _generation_key() -> str:
    return f"{config.TAGS_CACHE_PREFIX}:generation"


def invalidate() -> None:
    client = get_client()
    if client is None:
        return
    try:
        # Rotating the namespace prevents an in-flight read from repopulating
        # current pages with old data. Old entries expire through their TTL.
        client.set(_generation_key(), uuid4().hex)
    except RedisError:
        logger.warning("Tag cache invalidation unavailable; entries expire by TTL")


def list_tags(db: Session, offset: int, limit: int) -> Page[TagRead]:
    client = get_client()
    key = None

    if client is not None:
        try:
            client.set(_generation_key(), uuid4().hex, nx=True)
            generation = client.get(_generation_key())

            if generation is not None:
                key = f"{config.TAGS_CACHE_PREFIX}:page:v2:{generation}:{offset}:{limit}"
                cached = client.get(key)

                if cached is not None:
                    return Page[TagRead].model_validate_json(cached)

        except (RedisError, ValidationError, UnicodeError):
            logger.warning("Tag cache read unavailable or invalid; using database")

    items, total = tags.list_tags(db, offset, limit)
    result = Page[TagRead](
        items=[TagRead.model_validate(tag) for tag in items],
        total=total,
        offset=offset,
        limit=limit,
    )

    if key is not None:
        try:
            client.set(
                key,
                result.model_dump_json(),
                ex=config.TAGS_CACHE_TTL_SECONDS,
            )
        except RedisError:
            logger.warning("Tag cache write unavailable; using database")

    return result
