import json
import os
import time


class CacheBackendUnavailable(RuntimeError):
    pass


class RedisJsonCache:
    def __init__(self, redis_client, prefix: str = "cache"):
        self._r = redis_client
        self._prefix = prefix

    def _k(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def get_json(self, key: str):
        try:
            raw = self._r.get(self._k(key))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            raise CacheBackendUnavailable(str(e)) from e

    def set_json(self, key: str, value, ttl_seconds: int):
        try:
            self._r.set(self._k(key), json.dumps(value), ex=int(ttl_seconds))
        except Exception as e:
            raise CacheBackendUnavailable(str(e)) from e


def cache_enabled() -> bool:
    v = os.getenv("CACHE_ENABLED", "1").strip().lower()
    return v not in ("0", "false", "no", "off", "")


def cache_ttl_seconds(default: int = 5) -> int:
    try:
        return max(1, int(os.getenv("CACHE_TTL_SECONDS", str(default))))
    except Exception:
        return default


def make_cache_key(path: str, extra: str = "") -> str:
    # Keep it deterministic and stable across replicas.
    # (We intentionally avoid query params since these endpoints are simple.)
    base = path.strip() or "/"
    if extra:
        base = f"{base}:{extra}"
    return base


def now_ms() -> int:
    return int(time.time() * 1000)


