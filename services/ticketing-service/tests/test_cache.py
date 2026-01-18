import fakeredis

from cache import RedisJsonCache, make_cache_key


def test_cache_set_get_json_roundtrip():
    r = fakeredis.FakeRedis(decode_responses=True)
    c = RedisJsonCache(r, prefix="test")

    key = make_cache_key("/events")
    payload = [{"id": 1, "name": "A"}]
    c.set_json(key, payload, ttl_seconds=30)

    assert c.get_json(key) == payload


