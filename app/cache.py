import json
from typing import Any

import redis

from app.config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
        )
    return _client


def cache_tool_result(key: str, value: Any, ttl_seconds: int = 300) -> None:
    """Cache a tool call result so parallel agents don't re-fetch the same
    evidence window twice within one investigation run."""
    get_redis().set(key, json.dumps(value, default=str), ex=ttl_seconds)


def get_cached_tool_result(key: str) -> Any | None:
    raw = get_redis().get(key)
    return json.loads(raw) if raw else None


def set_investigation_state(incident_id: str, state: dict) -> None:
    get_redis().set(f"investigation:{incident_id}:state", json.dumps(state, default=str), ex=3600)


def get_investigation_state(incident_id: str) -> dict | None:
    raw = get_redis().get(f"investigation:{incident_id}:state")
    return json.loads(raw) if raw else None
