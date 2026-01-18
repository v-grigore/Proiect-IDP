import time


class RateLimiterBackendUnavailable(RuntimeError):
    pass


class InMemorySlidingWindowRateLimiter:
    """
    Sliding window limiter in-memory.
    NOTE: Works only per-process; not suitable for multiple replicas.
    """

    def __init__(self):
        self._store = {}

    def allow(self, key: str, limit: int, window_seconds: int, now_ms: int | None = None) -> bool:
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        window_ms = int(window_seconds) * 1000
        cutoff = now_ms - window_ms

        timestamps = [t for t in self._store.get(key, []) if t > cutoff]
        if len(timestamps) >= int(limit):
            self._store[key] = timestamps
            return False
        timestamps.append(now_ms)
        self._store[key] = timestamps
        return True


class RedisSlidingWindowRateLimiter:
    """
    Sliding window limiter stored in Redis ZSET (atomic via Lua).
    Works across replicas.
    """

    _LUA = r"""
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local ttl_seconds = tonumber(ARGV[4])

-- Drop old entries
redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms - window_ms)

local count = redis.call('ZCARD', key)
if count >= limit then
  redis.call('EXPIRE', key, ttl_seconds)
  return 0
end

redis.call('ZADD', key, now_ms, tostring(now_ms))
redis.call('EXPIRE', key, ttl_seconds)
return 1
"""

    def __init__(self, redis_client, prefix: str = "rl"):
        self._r = redis_client
        self._prefix = prefix

    def allow(self, key: str, limit: int, window_seconds: int, now_ms: int | None = None) -> bool:
        if now_ms is None:
            now_ms = int(time.time() * 1000)

        window_ms = int(window_seconds) * 1000
        ttl_seconds = int(window_seconds) + 2
        redis_key = f"{self._prefix}:{key}"

        try:
            res = self._r.eval(self._LUA, 1, redis_key, now_ms, window_ms, int(limit), ttl_seconds)
            return bool(res)
        except Exception as e:
            raise RateLimiterBackendUnavailable(str(e)) from e


