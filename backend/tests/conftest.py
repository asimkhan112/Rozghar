"""Test configuration.

Environment variables are set before anything imports the application, because
the engine is constructed at import time from settings.
"""

import os

# NullPool under test: each helper runs its own `asyncio.run()`, and a pooled
# asyncpg connection is bound to the loop that created it. Reusing one across
# loops raises "Event loop is closed". Pooling is a production concern anyway.
os.environ.setdefault("ENVIRONMENT", "test")

# The scheduler starts in the application lifespan, and `TestClient` runs the
# lifespan. Left enabled, every test that constructs a client would kick off
# background work against the same database the assertions read from.
os.environ.setdefault("SCHEDULER_ENABLED", "false")

# The suite logs in far more than ten times in five minutes, and hammers the
# admin API from a single address — both deliberately. Rate limiting on would
# make the tests assert on the limiter rather than on the behaviour under it.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

# Caching off for the same reason in reverse: almost every test writes data and
# then immediately asserts on a read of it. A ten-minute dashboard cache would
# serve the previous test's numbers. The cache itself is covered directly in
# `test_ops.py` and end to end by hand.
os.environ.setdefault("CACHE_ENABLED", "false")


import pytest

from app.core.config import settings


@pytest.fixture
def no_race_window():
    """Disable the concurrent-refresh grace window.

    Reuse detection and the race exemption are the same code path separated
    only by elapsed time, so each is tested with the window set appropriately
    rather than by sleeping.
    """
    original = settings.refresh_race_window_seconds
    settings.refresh_race_window_seconds = 0
    yield
    settings.refresh_race_window_seconds = original
