"""Prometheus metrics.

Deliberately small. A metric nobody has agreed to alert on is a metric nobody
reads, and every one of them costs cardinality forever — so this exposes the
four questions an operator actually asks at 3am (is it up, is it slow, is it
erroring, is the background work running) and nothing else.

**Label cardinality is the trap.** The HTTP histogram is labelled by *route
template*, never by URL. Labelling by path would create a new time series for
every job slug ever requested, and a Prometheus instance with a million series
for one endpoint is a Prometheus instance nobody can query.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

#: A private registry rather than the global default. The default collects
#: process and GC metrics from every library that ever imported the package,
#: and makes the test suite order-dependent because registration is global.
registry = CollectorRegistry()

http_requests = Counter(
    "plenilo_http_requests_total",
    "HTTP requests by route template, method and status class.",
    labelnames=("method", "route", "status"),
    registry=registry,
)

http_duration = Histogram(
    "plenilo_http_request_duration_seconds",
    "Request duration by route template.",
    labelnames=("method", "route"),
    # Tuned to this API rather than left at the default: the interesting
    # boundary is 100ms (the search target) and 1s (visibly slow to a reader).
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=registry,
)

search_queries = Counter(
    "plenilo_search_queries_total",
    "Searches by the strategy tier that produced the results.",
    labelnames=("strategy",),
    registry=registry,
)

analytics_events = Counter(
    "plenilo_analytics_events_total",
    "Analytics events accepted and rejected at ingest.",
    labelnames=("outcome",),
    registry=registry,
)

task_runs = Counter(
    "plenilo_scheduled_task_runs_total",
    "Scheduled task executions by outcome.",
    labelnames=("task", "outcome"),
    registry=registry,
)

task_duration = Histogram(
    "plenilo_scheduled_task_duration_seconds",
    "Scheduled task duration.",
    labelnames=("task",),
    buckets=(0.1, 0.5, 1.0, 5.0, 15.0, 60.0, 300.0),
    registry=registry,
)

rate_limit_rejections = Counter(
    "plenilo_rate_limit_rejections_total",
    "Requests rejected by a rate limiter, by bucket.",
    labelnames=("bucket",),
    registry=registry,
)

build_info = Gauge(
    "plenilo_build_info",
    "Build and environment metadata; the value is always 1.",
    labelnames=("version", "environment"),
    registry=registry,
)


class MetricsService:
    """Thin recording surface, so call sites do not import prometheus_client."""

    @staticmethod
    def observe_request(*, method: str, route: str, status_code: int, duration: float) -> None:
        # Status *class*, not code: 404 and 410 answer the same question, and
        # one series per status code triples the cardinality for nothing.
        http_requests.labels(method=method, route=route, status=f"{status_code // 100}xx").inc()
        http_duration.labels(method=method, route=route).observe(duration)

    @staticmethod
    def observe_search(strategy: str) -> None:
        search_queries.labels(strategy=strategy).inc()

    @staticmethod
    def observe_ingest(*, accepted: int, rejected: int) -> None:
        if accepted:
            analytics_events.labels(outcome="accepted").inc(accepted)
        if rejected:
            analytics_events.labels(outcome="rejected").inc(rejected)

    @staticmethod
    def observe_task(*, task: str, outcome: str, duration_ms: int) -> None:
        task_runs.labels(task=task, outcome=outcome).inc()
        task_duration.labels(task=task).observe(duration_ms / 1000)

    @staticmethod
    def observe_rate_limit(bucket: str) -> None:
        rate_limit_rejections.labels(bucket=bucket).inc()

    @staticmethod
    def set_build_info(*, version: str, environment: str) -> None:
        build_info.labels(version=version, environment=environment).set(1)

    @staticmethod
    def render() -> tuple[bytes, str]:
        return generate_latest(registry), CONTENT_TYPE_LATEST


__all__ = ["MetricsService", "registry"]
