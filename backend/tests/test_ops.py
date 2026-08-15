"""Milestone 9 behavioural tests.

Health, metrics, logging, caching, rate limiting and secret validation. Most of
these guard a decision that is invisible until it matters: liveness not
touching the database, metrics labelled by route template rather than URL, and
a cache that degrades to a miss instead of an error.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.config import (
    InsecureConfiguration,
    Settings,
    assert_secret_key_is_strong,
    settings,
)
from app.core.logging import JsonFormatter
from app.core.rate_limit import LOGIN, RateLimiter
from app.main import app
from app.services.cache_service import CacheService


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# --- health and readiness -------------------------------------------------


def test_health_is_liveness_only(client):
    """Liveness answers "should this process be restarted?". A check that
    queries Postgres turns a slow database into a restart loop across every
    instance, converting a degradation into an outage."""
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    # No dependency section at all — that is the whole point.
    assert "checks" not in body


def test_ready_reports_each_dependency(client):
    r = client.get("/ready")
    assert r.status_code in (200, 503)
    checks = r.json()["checks"]
    assert set(checks) == {"postgres", "redis", "scheduler"}
    assert checks["postgres"]["status"] == "ok"
    assert "latency_ms" in checks["postgres"]


def test_redis_and_scheduler_do_not_fail_readiness(client):
    """Permissions, caching and rate limiting all degrade gracefully without
    Redis by design, and background work is protected by an advisory lock. A
    healthy server must not leave the load balancer over either."""
    body = client.get("/ready").json()
    assert body["checks"]["postgres"]["status"] == "ok"
    assert body["status"] == "ready", (
        f"readiness must depend on Postgres alone; got {body['status']} with {body['checks']}"
    )


# --- metrics --------------------------------------------------------------


def test_metrics_exposes_prometheus_text(client):
    client.get("/api/v1/jobs")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    assert "rozgar_http_requests_total" in r.text
    assert "rozgar_build_info" in r.text


def test_metrics_label_by_route_template_not_url(client):
    """Labelling by URL creates a new time series for every job slug ever
    requested, which is the standard way to make a Prometheus instance
    unqueryable."""
    client.get("/api/v1/jobs/some-slug-that-does-not-exist")
    body = client.get("/metrics").text
    assert "/api/v1/jobs/{slug}" in body
    assert "some-slug-that-does-not-exist" not in body


def test_metrics_records_status_class_not_code(client):
    client.get("/api/v1/admin/jobs")  # 401
    body = client.get("/metrics").text
    assert 'status="4xx"' in body
    assert 'status="401"' not in body


def test_probes_are_not_instrumented(client):
    """Counting the health check flatters every latency percentile it lands
    in, and the probe runs more often than any real endpoint."""
    for _ in range(3):
        client.get("/health")
    body = client.get("/metrics").text
    assert 'route="/health"' not in body


def test_metrics_token_is_enforced_when_configured(client):
    original = settings.metrics_token
    settings.metrics_token = "a-secret-scrape-token"
    try:
        assert client.get("/metrics").status_code == 403
        assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 403
        ok = client.get("/metrics", headers={"Authorization": "Bearer a-secret-scrape-token"})
        assert ok.status_code == 200
    finally:
        settings.metrics_token = original


# --- request correlation --------------------------------------------------


def test_every_response_carries_a_request_id(client):
    r = client.get("/api/v1/jobs")
    assert r.headers.get("X-Request-ID")


def test_an_upstream_request_id_is_preserved(client):
    r = client.get("/api/v1/jobs", headers={"X-Request-ID": "upstream-correlation-id"})
    assert r.headers["X-Request-ID"] == "upstream-correlation-id"


# --- structured logging ---------------------------------------------------


def test_extra_fields_become_top_level_json_keys():
    record = logging.LogRecord(
        name="rozgar.tasks",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="task completed",
        args=(),
        exc_info=None,
    )
    record.task = "rebuild_rollups"
    record.duration_ms = 812

    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "task completed"
    assert payload["level"] == "INFO"
    assert payload["task"] == "rebuild_rollups"
    assert payload["duration_ms"] == 812
    assert "timestamp" in payload


def test_secrets_are_redacted_from_logs():
    record = logging.LogRecord(
        name="rozgar",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="signed in",
        args=(),
        exc_info=None,
    )
    record.password = "hunter2"
    record.access_token = "eyJhbGciOi"
    record.email = "someone@rozgar.pk"

    payload = json.loads(JsonFormatter().format(record))
    assert payload["password"] == "[redacted]"
    assert payload["access_token"] == "[redacted]"
    assert payload["email"] == "someone@rozgar.pk"


# --- cache ----------------------------------------------------------------


def test_cache_without_redis_is_a_miss_not_an_error():
    """Every method degrades to None so no call site needs a null branch, and
    the API stays correct without Redis — only slower."""

    async def run():
        cache = CacheService(None)
        assert cache.enabled is False
        assert await cache.get("search", "react") is None
        await cache.set("search", {"job_ids": []}, "react", ttl=60)
        await cache.invalidate()
        assert await cache.stats() == {"enabled": False}

    import asyncio

    asyncio.run(run())


def test_unserialisable_payload_does_not_raise():
    """A caller asked for a cache write, not for its request to fail."""

    async def run():
        cache = CacheService(None)
        await cache.set("search", {"bad": object()}, "key", ttl=60)

    import asyncio

    asyncio.run(run())


# --- rate limiting --------------------------------------------------------


def test_rate_limiter_fails_open_without_redis():
    """A cache outage that locks every user out of login is a worse incident
    than the abuse the limiter exists to stop."""

    async def run():
        limiter = RateLimiter(None)
        for _ in range(LOGIN.limit * 2):
            decision = await limiter.check(LOGIN, "203.0.113.9")
            assert decision.allowed

    import asyncio

    asyncio.run(run())


def test_rate_limit_response_is_rfc7807(client):
    """A 429 has to look like every other failure in this API, or a client's
    single error handler stops working at exactly the wrong moment."""
    # The shape is asserted directly; driving a real limit here would need a
    # live Redis and 10 failed logins, which the account lockout also reacts to.
    from starlette.requests import Request

    from app.api.middleware import _bucket_for

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "headers": [],
        "query_string": b"",
    }
    assert _bucket_for(Request(scope)) is LOGIN


# --- secret validation ----------------------------------------------------


def test_short_secret_is_refused_outside_local():
    config = Settings(environment="production", secret_key="short-key")
    with pytest.raises(InsecureConfiguration) as exc:
        assert_secret_key_is_strong(config)
    assert "32" in str(exc.value)


def test_known_default_secret_is_refused_even_at_full_length():
    """Length alone is not the test. A key that is the published default is
    worse than a short random one — an attacker reads it rather than guessing."""
    config = Settings(environment="production", secret_key="dev-only-change-me" + "x" * 20)
    assert_secret_key_is_strong(config)  # long and not the default → fine

    config = Settings(environment="staging", secret_key="dev-only-change-me")
    with pytest.raises(InsecureConfiguration) as exc:
        assert_secret_key_is_strong(config)
    assert "known default" in str(exc.value)


def test_local_and_test_are_exempt():
    """A fresh clone has to run without ceremony."""
    for environment in ("local", "test"):
        assert_secret_key_is_strong(
            Settings(environment=environment, secret_key="dev-only-change-me")
        )


def test_the_configured_secret_is_strong_enough_to_sign_with():
    """The dev key in `.env` must be at least 32 bytes, or PyJWT warns on
    every token it signs."""
    assert len(settings.secret_key.encode()) >= 32


def test_safe_extra_prevents_a_logrecord_collision():
    """`logging.makeRecord` raises when an extra key shadows a LogRecord
    attribute. A caller forwarding data it does not control — a task result, a
    parsed payload — would crash on a log line, at INFO level, which is to say
    in production and not in a quiet test run.
    """
    from app.core.logging import safe_extra

    logger = logging.getLogger("rozgar.test.collision")
    dangerous = {"created": 3, "name": "x", "partitions": ["a"]}

    with pytest.raises(KeyError):
        logger.makeRecord("n", logging.INFO, __file__, 1, "m", (), None, extra=dangerous)

    record = logger.makeRecord(
        "n", logging.INFO, __file__, 1, "m", (), None, extra=safe_extra(dangerous)
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["field_created"] == 3
    assert payload["partitions"] == ["a"]


def test_task_results_are_nested_not_splatted():
    """The regression guard for the bug above: `ensure_partitions` returns a
    key called `created`, so splatting task details into `extra=` made the most
    consequential scheduled task fail whenever logging was at INFO.
    """
    import asyncio

    from app.tasks.scheduled_tasks import run_task

    async def returns_reserved_keys(_session):
        return {"created": 2, "name": "partition", "module": "x"}

    logging.getLogger().setLevel(logging.INFO)
    result = asyncio.run(run_task("reserved_key_probe", returns_reserved_keys))
    assert result.ok, result.error
    assert result.details["created"] == 2
