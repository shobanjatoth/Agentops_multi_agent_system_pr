# import os
# import time

# import pytest

# from app.approval import ApprovalStore
# from app.cache import Cache

# REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


# def _redis_available() -> bool:
#     try:
#         import redis as redis_lib

#         redis_lib.from_url(REDIS_URL, socket_connect_timeout=1.0).ping()
#         return True
#     except Exception:
#         return False


# REDIS_UP = _redis_available()
# requireimports_redis = pytest.mark.skipif(not REDIS_UP, reason="No Redis instance reachable for this test run")


# # ---- in-memory backend (always runs, no external dependency) ----

# def test_memory_backend_basic_get_set_delete(monkeypatch):
#     monkeypatch.delenv("REDIS_URL", raising=False)
#     cache = Cache(redis_url=None, namespace="test-mem")
#     assert cache.backend_name == "memory"
#     assert cache.get_json("k1") is None

#     cache.set_json("k1", {"hello": "world"})
#     assert cache.get_json("k1") == {"hello": "world"}

#     cache.delete("k1")
#     assert cache.get_json("k1") is None


# def test_memory_backend_ttl_expiry(monkeypatch):
#     monkeypatch.delenv("REDIS_URL", raising=False)
#     cache = Cache(redis_url=None, namespace="test-ttl")
#     cache.set_json("expiring", "value", ttl_seconds=1)
#     assert cache.get_json("expiring") == "value"
#     time.sleep(1.2)
#     assert cache.get_json("expiring") is None


# def test_memory_backend_keys_prefix_scan(monkeypatch):
#     monkeypatch.delenv("REDIS_URL", raising=False)
#     cache = Cache(redis_url=None, namespace="test-keys")
#     cache.set_json("approval:task-1", {"a": 1})
#     cache.set_json("approval:task-2", {"b": 2})
#     cache.set_json("other:task-3", {"c": 3})
#     keys = cache.keys("approval:")
#     assert set(keys) == {"approval:task-1", "approval:task-2"}


# def test_cache_falls_back_when_redis_unreachable():
#     # Port 1 is never a real Redis server -- connection should fail fast
#     # and the cache should degrade to memory instead of raising.
#     cache = Cache(redis_url="redis://localhost:1/0", namespace="test-fallback")
#     assert cache.backend_name == "memory-fallback"
#     cache.set_json("k", "v")
#     assert cache.get_json("k") == "v"


# # ---- real Redis integration (only runs when a Redis instance is reachable) ----

# @requires_redis
# def test_cache_uses_real_redis_when_configured():
#     cache = Cache(redis_url=REDIS_URL, namespace="test-real-redis")
#     assert cache.backend_name == "redis"
#     cache.set_json("k", {"nested": [1, 2, 3]}, ttl_seconds=10)
#     assert cache.get_json("k") == {"nested": [1, 2, 3]}
#     cache.delete("k")
#     assert cache.get_json("k") is None


# @requires_redis
# def test_approval_store_persists_across_separate_instances_via_redis():
#     """
#     This is the actual bug the Redis integration fixes: with the old
#     in-memory-only ApprovalStore, a second ApprovalStore() instance
#     (simulating a second worker process, or the same process after a
#     restart) would have no idea a task was pending. With Redis as the
#     backing store, it does.
#     """
#     shared_cache = Cache(redis_url=REDIS_URL, namespace="test-approval-shared")

#     store_a = ApprovalStore(cache=shared_cache)
#     store_a.add("task-cross-worker", {"type": "merge_pr", "body": "x"}, risk_score=0.9)

#     # A brand-new ApprovalStore pointed at the same Redis namespace --
#     # simulating a different process entirely.
#     store_b = ApprovalStore(cache=Cache(redis_url=REDIS_URL, namespace="test-approval-shared"))
#     pending = store_b.pending()
#     assert "task-cross-worker" in pending

#     resolved = store_b.resolve("task-cross-worker", approved=True)
#     assert resolved["action"]["type"] == "merge_pr"

#     # cleanup
#     store_a.clear()






















from __future__ import annotations

import os
import time

import pytest
import redis as redis_lib
from dotenv import load_dotenv

from app.approval import ApprovalStore
from app.cache import Cache


# Load project environment variables before reading REDIS_URL.
load_dotenv(override=False)

REDIS_URL = os.getenv("REDIS_URL")


def _redis_available() -> bool:
    if not REDIS_URL:
        return False

    client = None

    try:
        client = redis_lib.from_url(
            REDIS_URL,
            socket_connect_timeout=5,
            socket_timeout=5,
            decode_responses=True,
        )

        return bool(client.ping())

    except Exception:
        return False

    finally:
        if client is not None:
            client.close()


REDIS_UP = _redis_available()

requires_redis = pytest.mark.skipif(
    not REDIS_UP,
    reason="Upstash Redis is not reachable for this test run",
)


# --------------------------------------------------
# In-memory backend tests
# --------------------------------------------------

def test_memory_backend_basic_get_set_delete(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)

    cache = Cache(redis_url=None, namespace="test-mem")

    assert cache.backend_name == "memory"
    assert cache.get_json("k1") is None

    cache.set_json("k1", {"hello": "world"})

    assert cache.get_json("k1") == {"hello": "world"}

    cache.delete("k1")

    assert cache.get_json("k1") is None


def test_memory_backend_ttl_expiry(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)

    cache = Cache(redis_url=None, namespace="test-ttl")

    cache.set_json("expiring", "value", ttl_seconds=1)

    assert cache.get_json("expiring") == "value"

    time.sleep(1.2)

    assert cache.get_json("expiring") is None


def test_memory_backend_keys_prefix_scan(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)

    cache = Cache(redis_url=None, namespace="test-keys")

    cache.set_json("approval:task-1", {"a": 1})
    cache.set_json("approval:task-2", {"b": 2})
    cache.set_json("other:task-3", {"c": 3})

    keys = cache.keys("approval:")

    assert set(keys) == {
        "approval:task-1",
        "approval:task-2",
    }


def test_cache_falls_back_when_redis_unreachable():
    cache = Cache(
        redis_url="redis://localhost:1/0",
        namespace="test-fallback",
    )

    assert cache.backend_name == "memory-fallback"

    cache.set_json("k", "v")

    assert cache.get_json("k") == "v"


# --------------------------------------------------
# Real Upstash Redis integration tests
# --------------------------------------------------

@requires_redis
def test_cache_uses_real_redis_when_configured():
    cache = Cache(
        redis_url=REDIS_URL,
        namespace="test-real-redis",
    )

    assert cache.backend_name == "redis"

    cache.set_json(
        "k",
        {"nested": [1, 2, 3]},
        ttl_seconds=10,
    )

    assert cache.get_json("k") == {"nested": [1, 2, 3]}

    cache.delete("k")

    assert cache.get_json("k") is None


@requires_redis
def test_approval_store_persists_across_separate_instances_via_redis():
    """
    Verify that separate ApprovalStore instances share pending
    approvals through Redis.
    """

    namespace = "test-approval-shared"

    shared_cache = Cache(
        redis_url=REDIS_URL,
        namespace=namespace,
    )

    store_a = ApprovalStore(cache=shared_cache)

    store_a.add(
        "task-cross-worker",
        {"type": "merge_pr", "body": "x"},
        risk_score=0.9,
    )

    store_b = ApprovalStore(
        cache=Cache(
            redis_url=REDIS_URL,
            namespace=namespace,
        )
    )

    try:
        pending = store_b.pending()

        assert "task-cross-worker" in pending

        resolved = store_b.resolve(
            "task-cross-worker",
            approved=True,
        )

        assert resolved["action"]["type"] == "merge_pr"

    finally:
        store_a.clear()
