import redis.asyncio as redis

_redis_client: redis.Redis | None = None


def init_redis(url: str) -> redis.Redis:
    """Initialize the Redis client. Called during app startup."""
    global _redis_client
    _redis_client = redis.from_url(url, decode_responses=True)
    return _redis_client


async def close_redis() -> None:
    """Close the Redis client. Called during app shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


def get_redis() -> redis.Redis:
    """FastAPI dependency for Redis access."""
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized. Call init_redis() first.")
    return _redis_client
