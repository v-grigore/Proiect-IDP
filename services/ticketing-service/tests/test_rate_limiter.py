import fakeredis

from rate_limiter import RedisSlidingWindowRateLimiter


def test_redis_rate_limiter_allows_then_blocks_then_allows_after_window():
    r = fakeredis.FakeRedis(decode_responses=True)
    limiter = RedisSlidingWindowRateLimiter(r, prefix="test")

    key = "user123:/events/1/tickets"
    limit = 2
    window_seconds = 60

    now = 1_000_000
    assert limiter.allow(key, limit, window_seconds, now_ms=now) is True
    assert limiter.allow(key, limit, window_seconds, now_ms=now + 1) is True
    assert limiter.allow(key, limit, window_seconds, now_ms=now + 2) is False

    # after window passes -> allowed again
    assert limiter.allow(key, limit, window_seconds, now_ms=now + (window_seconds * 1000) + 10) is True


