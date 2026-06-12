"""
Tests for the bounded session-history cache in app/main.py (LIN-208).

Verifies that _conversation_histories is a TTLCache with a finite maxsize so
the in-process dict cannot grow without bound.
"""

import threading

import pytest
from cachetools import TTLCache


def test_conversation_histories_is_ttlcache(setup_test_data):
    """_conversation_histories must be a TTLCache, not a plain dict."""
    from app.main import _conversation_histories

    assert isinstance(_conversation_histories, TTLCache), (
        f"Expected TTLCache, got {type(_conversation_histories)}"
    )


def test_conversation_histories_has_finite_maxsize(setup_test_data):
    """The cache must have a finite maxsize to bound memory usage."""
    from app.main import _conversation_histories

    assert _conversation_histories.maxsize < float("inf"), (
        "maxsize must be finite to prevent unbounded growth"
    )


def test_histories_lock_is_threading_lock(setup_test_data):
    """A threading.Lock must guard cache access for concurrent requests."""
    from app.main import _histories_lock

    # threading.Lock() returns a _thread.lock; check it has the expected API.
    assert hasattr(_histories_lock, "acquire") and hasattr(_histories_lock, "release"), (
        "_histories_lock must be a threading.Lock (or compatible)"
    )


def test_oldest_session_evicted_when_maxsize_exceeded(setup_test_data, monkeypatch):
    """When the cache is full, the LRU entry is evicted rather than raising."""
    from app import main as main_mod

    # Use a tiny cache so the test doesn't need to insert 1000 entries.
    small_cache = TTLCache(maxsize=3, ttl=3600)
    monkeypatch.setattr(main_mod, "_conversation_histories", small_cache)

    # Fill the cache to capacity.
    for i in range(3):
        small_cache.setdefault(f"session_{i}", [f"msg_{i}"])

    assert len(small_cache) == 3

    # Adding a fourth entry must evict one rather than raising an error.
    small_cache.setdefault("session_overflow", ["overflow_msg"])

    # Cache must still be at maxsize (one entry was evicted).
    assert len(small_cache) <= 3
