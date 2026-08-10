import json
import logging
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.config import get_settings

logger = logging.getLogger(__name__)
_client: Redis | None = None


def get_redis_client() -> Redis | None:
    """Return a lazy Redis client, or None when cache is disabled."""
    global _client
    redis_url = get_settings().redis_url
    if not redis_url:
        return None
    if _client is None:
        _client = Redis.from_url(redis_url, decode_responses=True)
    return _client


def cache_get(key: str) -> Any | None:
    client = get_redis_client()
    if client is None:
        return None
    try:
        value = client.get(key)
        return json.loads(value) if value is not None else None
    except (RedisError, json.JSONDecodeError):
        logger.warning("Redis cache read failed", exc_info=True)
        return None


def cache_set(key: str, value: Any) -> None:
    client = get_redis_client()
    if client is None:
        return
    try:
        client.setex(key, get_settings().redis_cache_ttl_seconds, json.dumps(value))
    except (RedisError, TypeError):
        logger.warning("Redis cache write failed", exc_info=True)


def cache_delete(*keys: str) -> None:
    client = get_redis_client()
    if client is None or not keys:
        return
    try:
        client.delete(*keys)
    except RedisError:
        logger.warning("Redis cache invalidation failed", exc_info=True)


def redis_is_ready() -> bool | None:
    client = get_redis_client()
    if client is None:
        return None
    try:
        return bool(client.ping())
    except RedisError:
        return False
