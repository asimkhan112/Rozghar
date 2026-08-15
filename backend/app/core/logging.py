"""Structured JSON logging.

A stdlib `Formatter` rather than `structlog`, for one reason: every existing
`logger.info("...", extra={...})` call in this codebase keeps working
unchanged. Adopting a logging library would mean rewriting every call site to
get the benefit, and the benefit here is one function.

`extra=` fields land as top-level JSON keys, which is what makes the scheduler's
`{"event": "task.completed", "task": "rebuild_rollups", "duration_ms": 812}`
queryable rather than a sentence someone has to grep.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

#: Attributes every LogRecord carries. Anything else came from `extra=` and is
#: therefore a field the caller deliberately attached.
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)

#: Reserved names a caller might plausibly reach for. `logging.makeRecord`
#: raises on these before any formatter runs, so `safe_extra` renames rather
#: than relying on the formatter to cope.
_COLLIDES = frozenset({"created", "name", "module", "filename", "message", "asctime", "levelname"})

#: Keys that must never reach a log line, whatever a caller passes.
_REDACT = frozenset(
    {"password", "token", "access_token", "refresh_token", "secret", "authorization", "api_key"}
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = "[redacted]" if key.lower() in _REDACT else _safe(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str)


def safe_extra(fields: dict[str, Any]) -> dict[str, Any]:
    """Make an arbitrary dict safe to pass as `extra=`.

    `logging.makeRecord` raises `KeyError` when an extra key shadows a
    LogRecord attribute, so a caller forwarding data it does not control —
    a task result, a parsed payload — can crash on a log line. Colliding keys
    are prefixed rather than dropped: losing the value silently would be the
    same bug one layer down.
    """
    return {(f"field_{k}" if k in _COLLIDES else k): v for k, v in fields.items()}


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list | tuple):
        return [_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _safe(v) for k, v in value.items()}
    return str(value)


def configure_logging(*, json_logs: bool, debug: bool) -> None:
    """Install the formatter on the root handler.

    Plain text stays available for local work — JSON in a terminal is a wall
    someone has to pipe through `jq` to read, and making local development
    worse is how a logging change gets reverted.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if json_logs
        else logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # Uvicorn installs its own handlers; without this every line is emitted
    # twice, once structured and once not.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True


__all__ = ["JsonFormatter", "configure_logging", "safe_extra"]
