"""UUIDv7 generation (RFC 9562).

Time-ordered identifiers keep B-tree inserts local instead of scattering them
across the index the way random UUIDv4 does. PostgreSQL 16 has no native
`uuidv7()` — that arrives in 18 — so keys are generated application-side.

Layout, 128 bits total:

    48 bits   unix timestamp in milliseconds
     4 bits   version (0b0111)
    12 bits   sub-millisecond counter, for ordering within the same millisecond
     2 bits   variant (0b10)
    62 bits   random
"""

import os
import threading
import time
from uuid import UUID

_lock = threading.Lock()
_last_timestamp_ms = -1
_counter = 0

_MAX_COUNTER = 0xFFF  # 12 bits


def uuid7() -> UUID:
    """Return a time-ordered UUIDv7.

    Monotonic within a process: two calls in the same millisecond increment a
    counter rather than relying on random bits, so generation order and sort
    order agree. If the counter saturates, generation waits for the next
    millisecond instead of wrapping and breaking ordering.
    """
    global _last_timestamp_ms, _counter

    with _lock:
        timestamp_ms = time.time_ns() // 1_000_000

        if timestamp_ms == _last_timestamp_ms:
            _counter += 1
            if _counter > _MAX_COUNTER:
                # Counter exhausted for this millisecond — spin to the next one.
                while timestamp_ms <= _last_timestamp_ms:
                    timestamp_ms = time.time_ns() // 1_000_000
                _counter = 0
        elif timestamp_ms < _last_timestamp_ms:
            # Clock moved backwards (NTP correction). Hold the previous
            # timestamp and keep counting so ordering never regresses.
            timestamp_ms = _last_timestamp_ms
            _counter += 1
        else:
            _counter = 0

        _last_timestamp_ms = timestamp_ms
        counter = _counter

    value = timestamp_ms << 80
    value |= 0x7 << 76
    value |= counter << 64
    value |= 0b10 << 62
    value |= int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)

    return UUID(int=value)


def timestamp_of(value: UUID) -> float:
    """Extract the embedded creation time as a Unix timestamp in seconds."""
    return (value.int >> 80) / 1000.0
