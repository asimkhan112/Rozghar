"""Test configuration.

Environment variables are set before anything imports the application, because
the engine is constructed at import time from settings.
"""

import os

# NullPool under test: each helper runs its own `asyncio.run()`, and a pooled
# asyncpg connection is bound to the loop that created it. Reusing one across
# loops raises "Event loop is closed". Pooling is a production concern anyway.
os.environ.setdefault("ENVIRONMENT", "test")


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
