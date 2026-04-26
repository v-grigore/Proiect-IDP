import fakeredis

from rate_limiter import RedisSlidingWindowRateLimiter


def test_redis_rate_limiter_blocks_after_limit():
    r = fakeredis.FakeRedis(decode_responses=True)
    limiter = RedisSlidingWindowRateLimiter(r, prefix="test")

    key = "user123:/payments/start"
    limit = 2
    window_seconds = 60
    now = 1_000_000

    assert limiter.allow(key, limit, window_seconds, now_ms=now) is True
    assert limiter.allow(key, limit, window_seconds, now_ms=now + 1) is True
    assert limiter.allow(key, limit, window_seconds, now_ms=now + 2) is False

