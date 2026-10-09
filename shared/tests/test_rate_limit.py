"""Shared sliding-window limiter unit tests (task 16)."""
import time

from xleuth_shared.rate_limit import SlidingWindowLimiter


def test_allows_up_to_limit_then_blocks_with_retry_after():
    lim = SlidingWindowLimiter()
    now = time.monotonic()
    for _ in range(5):
        ok, _ = lim.allow("k", 5, 60, now=now)
        assert ok
    ok, retry = lim.allow("k", 5, 60, now=now)
    assert not ok and retry > 0


def test_window_slides():
    lim = SlidingWindowLimiter()
    now = time.monotonic()
    for _ in range(2):
        assert lim.allow("k", 2, 10, now=now)[0]
    assert not lim.allow("k", 2, 10, now=now)[0]
    assert lim.allow("k", 2, 10, now=now + 11)[0]


def test_keys_are_independent():
    lim = SlidingWindowLimiter()
    now = time.monotonic()
    assert lim.allow("a", 1, 60, now=now)[0]
    assert not lim.allow("a", 1, 60, now=now)[0]
    assert lim.allow("b", 1, 60, now=now)[0]
