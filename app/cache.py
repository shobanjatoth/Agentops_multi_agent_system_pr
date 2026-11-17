# """
# Redis-backed cache with an automatic in-memory fallback.

# Two things use this:
#   1. ApprovalStore (app/approval.py) — pending human-approval state.
#      Without Redis, a server restart or a second Render/uvicorn worker
#      process loses every pending approval. That's a real production bug,
#      not a hypothetical one — this fixes it.
#   2. LLM response caching (app/llm.py) — identical (system, prompt) pairs
#      within the TTL window skip the network call entirely. Same pattern
#      as the AI Legal Advisor project's Redis TTL cache (~20x latency cut
#      on repeat queries, fewer LLM calls = lower cost).

# Same "Redis-backed, in-memory fallback" pattern used across the other
# projects: if REDIS_URL isn't set, or the Redis server is unreachable,
# everything keeps working with an in-process dict — degraded (no
# cross-process sharing, no persistence across restarts) but never down.
# """
# from __future__ import annotations

# import json
# import os
# import time
# from threading import Lock
# from typing import Any

# try:
#     import redis as redis_lib
# except ImportError:  # pragma: no cover — redis package is a hard requirement in requirements.txt
#     redis_lib = None


# class _InMemoryBackend:
#     """Fallback store: a plain dict with manual TTL expiry, thread-safe."""

#     def __init__(self):
#         self._data: dict[str, tuple[str, float | None]] = {}  # key -> (value, expires_at)
#         self._lock = Lock()

#     def get(self, key: str) -> str | None:
#         with self._lock:
#             entry = self._data.get(key)
#             if entry is None:
#                 return None
#             value, expires_at = entry
#             if expires_at is not None and time.time() > expires_at:
#                 del self._data[key]
#                 return None
#             return value

#     def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
#         with self._lock:
#             expires_at = time.time() + ttl_seconds if ttl_seconds else None
#             self._data[key] = (value, expires_at)

#     def delete(self, key: str) -> None:
#         with self._lock:
#             self._data.pop(key, None)

#     def keys(self, prefix: str) -> list[str]:
#         with self._lock:
#             return [k for k in self._data if k.startswith(prefix)]


# class Cache:
#     """
#     Unified get/set/delete interface. Tries Redis first (if configured
#     and reachable); transparently falls back to an in-memory backend
#     otherwise. `backend_name` tells you which one is actually active —
#     useful for a startup log line or a /health check.
#     """

#     def __init__(self, redis_url: str | None = None, namespace: str = "agentops"):
#         self.namespace = namespace
#         self._memory = _InMemoryBackend()
#         self._redis = None
#         self.backend_name = "memory"

#         redis_url = redis_url or os.getenv("REDIS_URL")
#         if redis_url and redis_lib is not None:
#             try:
#                 client = redis_lib.from_url(redis_url, socket_connect_timeout=1.5, decode_responses=True)
#                 client.ping()
#                 self._redis = client
#                 self.backend_name = "redis"
#             except Exception:
#                 # Redis configured but unreachable (down, wrong URL, network
#                 # blocked) -- degrade to in-memory rather than crash the app.
#                 self._redis = None
#                 self.backend_name = "memory-fallback"

#     def _k(self, key: str) -> str:
#         return f"{self.namespace}:{key}"

#     def get_json(self, key: str) -> Any | None:
#         raw = self._redis.get(self._k(key)) if self._redis else self._memory.get(self._k(key))
#         return json.loads(raw) if raw is not None else None

#     def set_json(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
#         raw = json.dumps(value)
#         if self._redis:
#             if ttl_seconds:
#                 self._redis.setex(self._k(key), ttl_seconds, raw)
#             else:
#                 self._redis.set(self._k(key), raw)
#         else:
#             self._memory.set(self._k(key), raw, ttl_seconds)

#     def delete(self, key: str) -> None:
#         if self._redis:
#             self._redis.delete(self._k(key))
#         else:
#             self._memory.delete(self._k(key))

#     def keys(self, prefix: str = "") -> list[str]:
#         full_prefix = self._k(prefix)
#         if self._redis:
#             return [k[len(self.namespace) + 1:] for k in self._redis.keys(f"{full_prefix}*")]
#         return [k[len(self.namespace) + 1:] for k in self._memory.keys(full_prefix)]









from __future__ import annotations

import json
import logging
import os
import time
from threading import Lock
from typing import Any

try:
    import redis as redis_lib
except ImportError:  # pragma: no cover
    redis_lib = None


logger = logging.getLogger(__name__)


class _InMemoryBackend:
    """Thread-safe in-memory store with TTL expiration."""

    def __init__(self):
        self._data: dict[str, tuple[str, float | None]] = {}
        self._lock = Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            entry = self._data.get(key)

            if entry is None:
                return None

            value, expires_at = entry

            if expires_at is not None and time.time() >= expires_at:
                del self._data[key]
                return None

            return value

    def set(
        self,
        key: str,
        value: str,
        ttl_seconds: int | None = None,
    ) -> None:
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        with self._lock:
            expires_at = (
                time.time() + ttl_seconds
                if ttl_seconds is not None
                else None
            )

            self._data[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def keys(self, prefix: str) -> list[str]:
        with self._lock:
            now = time.time()

            expired = [
                key
                for key, (_, expires_at) in self._data.items()
                if expires_at is not None and now >= expires_at
            ]

            for key in expired:
                del self._data[key]

            return [
                key
                for key in self._data
                if key.startswith(prefix)
            ]


class Cache:
    """
    Redis-backed cache with in-memory fallback.

    Redis is preferred when configured and reachable.
    Falls back to memory when Redis operations fail.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        namespace: str = "agentops",
    ):
        self.namespace = namespace
        self._memory = _InMemoryBackend()
        self._redis = None
        self._redis_url = redis_url or os.getenv("REDIS_URL")
        self.backend_name = "memory"

        if self._redis_url and redis_lib is not None:
            self._connect_redis()

    def _connect_redis(self) -> bool:
        if not self._redis_url or redis_lib is None:
            return False

        try:
            client = redis_lib.from_url(
                self._redis_url,
                socket_connect_timeout=5,
                socket_timeout=5,
                decode_responses=True,
                health_check_interval=30,
            )

            client.ping()

            self._redis = client
            self.backend_name = "redis"

            logger.info("Redis cache connected successfully")
            return True

        except Exception:
            self._redis = None
            self.backend_name = "memory-fallback"

            logger.exception(
                "Redis connection failed. Using in-memory cache."
            )

            return False

    def _k(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def _fallback(self) -> None:
        self._redis = None
        self.backend_name = "memory-fallback"

    def get_json(self, key: str) -> Any | None:
        full_key = self._k(key)

        if self._redis:
            try:
                raw = self._redis.get(full_key)
                return json.loads(raw) if raw is not None else None

            except Exception:
                logger.exception("Redis GET failed")
                self._fallback()

        raw = self._memory.get(full_key)
        return json.loads(raw) if raw is not None else None

    def set_json(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        full_key = self._k(key)
        raw = json.dumps(value)

        if self._redis:
            try:
                if ttl_seconds is not None:
                    self._redis.setex(full_key, ttl_seconds, raw)
                else:
                    self._redis.set(full_key, raw)

                return

            except Exception:
                logger.exception("Redis SET failed")
                self._fallback()

        self._memory.set(full_key, raw, ttl_seconds)

    def delete(self, key: str) -> None:
        full_key = self._k(key)

        if self._redis:
            try:
                self._redis.delete(full_key)
                return

            except Exception:
                logger.exception("Redis DELETE failed")
                self._fallback()

        self._memory.delete(full_key)

    def keys(self, prefix: str = "") -> list[str]:
        full_prefix = self._k(prefix)

        if self._redis:
            try:
                result = []

                for key in self._redis.scan_iter(
                    match=f"{full_prefix}*",
                    count=100,
                ):
                    result.append(
                        key[len(self.namespace) + 1:]
                    )

                return result

            except Exception:
                logger.exception("Redis SCAN failed")
                self._fallback()

        return [
            key[len(self.namespace) + 1:]
            for key in self._memory.keys(full_prefix)
        ]
