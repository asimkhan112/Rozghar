"""Application configuration.

Every setting is typed and read from the environment. Missing required values
raise at import time rather than at first use, so a misconfigured deployment
fails on startup instead of on the first request that happens to need them.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Query parameters libpq understands and asyncpg does not. Passing them
#: through produces `connect() got an unexpected keyword argument 'sslmode'`
#: at first connection — a failure that only appears against a hosted database,
#: never locally, which is the worst place for it to first show up.
_LIBPQ_ONLY_PARAMS = frozenset({"sslmode", "channel_binding", "target_session_attrs", "options"})


def _as_driver_url(raw: str, driver: Literal["asyncpg", "psycopg2"]) -> str:
    """Rewrite a hosted-Postgres URL for a specific SQLAlchemy driver.

    Two things have to change. The scheme has to name the driver, because
    providers hand out bare `postgres://` or `postgresql://`. And for asyncpg
    the libpq-only query parameters have to come off; TLS is requested through
    `connect_args` instead, which is what `database_requires_ssl` is for.
    """
    url = raw.strip()
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = url[len(prefix):]
            break

    if driver == "asyncpg":
        base, _, query = url.partition("?")
        kept = [
            part
            for part in query.split("&")
            if part and part.split("=")[0].lower() not in _LIBPQ_ONLY_PARAMS
        ]
        url = f"{base}?{'&'.join(kept)}" if kept else base

    return f"postgresql+{driver}://{url}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- application -----------------------------------------------------
    app_name: str = "Plenilo API"
    app_version: str = "0.9.0"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    #: Where generated binary assets live. Relative to the working
    #: directory in development; an absolute path in a container, mounted on a
    #: volume that survives a restart.
    storage_root: str = "storage"

    #: Public origin, used to build absolute URLs the application does not
    #: serve itself — sitemap entries, canonical links, structured data.
    #: Relative URLs are invalid in all three, so this cannot be derived from
    #: the request: a sitemap fetched through a proxy would otherwise advertise
    #: the proxy's internal hostname to Google.
    site_url: str = "http://localhost:8443"

    # --- database --------------------------------------------------------
    #: A complete connection string, which is how hosted Postgres is supplied:
    #: Neon, Railway, Supabase and Heroku all hand out one URL rather than five
    #: separate settings. When present it wins; when absent the `postgres_*`
    #: parts below are assembled instead, so a local checkout still runs with
    #: no configuration at all.
    #:
    #: Nothing else in the application reads it — `database_url` and
    #: `sync_database_url` remain the only two accessors, so moving between
    #: hosts is an environment change rather than a code change.
    database_url_override: str = Field(default="", alias="DATABASE_URL")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "rozgar"
    postgres_password: str = "rozgar"
    postgres_db: str = "rozgar"

    #: Pool sizing stays below the Postgres connection limit. PgBouncer sits in
    #: front of this in anything above local.
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout: int = 30
    db_echo: bool = False

    # --- redis -----------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # --- security --------------------------------------------------------
    #: Signs access tokens and keys the IP hash. `min_length` is 32 because
    #: HMAC-SHA256 has a 32-byte block: a shorter key is zero-padded, so it
    #: contributes less entropy than its length suggests and PyJWT warns on
    #: every single token. Validated again at startup — see
    #: `assert_secret_key_is_strong` — because a key long enough to pass this
    #: check can still be the published default.
    secret_key: str = Field(default="dev-only-change-me", min_length=8)

    #: Emit JSON logs. Off locally, because JSON in a terminal is a wall a
    #: human has to pipe through `jq`, and making local work worse is how a
    #: logging change gets reverted.
    json_logs: bool = False

    #: When set, `/metrics` requires `Authorization: Bearer <token>`. Leave
    #: empty only when the port is genuinely unreachable from outside the
    #: cluster — the endpoint reveals traffic shape, route names and error
    #: rates.
    metrics_token: str = ""

    #: Rate limiting is Redis-backed and fails open. Off in tests, where the
    #: suite makes hundreds of calls from one address on purpose.
    rate_limit_enabled: bool = True

    #: Read caching. A separate switch from Redis being present, because
    #: "caching is off" is a legitimate operational state — during a backfill,
    #: while diagnosing a stale-data report, or in a test suite that asserts on
    #: what it just wrote.
    cache_enabled: bool = True
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60
    #: Window after rotation in which replaying a token counts as two tabs
    #: racing rather than theft. Long enough for a concurrent refresh, far too
    #: short to be useful to an attacker holding a captured token.
    refresh_race_window_seconds: int = 10
    #: Consecutive failed logins before the account locks.
    max_failed_login_attempts: int = 5
    account_lockout_minutes: int = 15

    # --- public reports --------------------------------------------------
    #: Submissions accepted from one hashed client address per window. The
    #: limit is deliberately generous: a reader who spots five dead links in a
    #: browsing session is the most valuable contributor the site has, not an
    #: attacker.
    report_rate_limit_per_window: int = 10
    report_rate_limit_window_minutes: int = 60

    # --- background jobs -------------------------------------------------
    #: The scheduler runs in-process. Disable it on any instance that should
    #: only serve requests — a cron container, a one-off shell, the test suite.
    scheduler_enabled: bool = True
    #: Every task takes a Postgres advisory lock before doing work, so running
    #: several API instances does not multiply the work. This is the safety
    #: property that makes in-process scheduling viable at all.
    scheduler_timezone: str = "Asia/Karachi"

    #: Partition window kept ahead of now. Six months is far more than the
    #: monthly task needs; the margin is what survives the scheduler being
    #: down for a while without ingest starting to reject inserts.
    partition_months_ahead: int = 6
    #: Retention. Analytics partitions older than this are dropped whole.
    analytics_retention_days: int = 400
    search_log_retention_days: int = 180
    #: Rollups are cheap and small; they outlive the raw events they came from.
    rollup_retention_days: int = 800

    #: Open reports on one listing before it is escalated in the logs.
    report_alert_threshold: int = 3

    # --- AI assistance ---------------------------------------------------
    #: Anthropic API key. Absent means the AI endpoints return 503 rather than
    #: failing at call time — an editor should be told the feature is off, not
    #: shown a stack trace.
    anthropic_api_key: str = ""

    #: The model the editorial tools call. Pinned rather than "latest" so a
    #: model release cannot silently change how every job description reads.
    ai_model: str = "claude-opus-5"

    #: Output ceiling per call. A generated description with all four sections
    #: runs ~800 tokens; this leaves room without letting a runaway response
    #: bill unbounded.
    ai_max_tokens: int = 4096

    #: Calls per admin per hour. Each one costs real money, and an editor who
    #: needs more than this in an hour is fighting the tool rather than using it.
    ai_rate_limit_per_hour: int = 40

    # --- startup ---------------------------------------------------------
    #: When true, a mismatch between the Permission enum and the permissions
    #: table aborts startup. Disabled only for the migration that seeds them.
    validate_permissions_on_startup: bool = True

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Async driver URL, used by the application at runtime."""
        if self.database_url_override:
            return _as_driver_url(self.database_url_override, "asyncpg")
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                path=self.postgres_db,
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        """Sync driver URL. Alembic runs migrations through this."""
        if self.database_url_override:
            return _as_driver_url(self.database_url_override, "psycopg2")
        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg2",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                path=self.postgres_db,
            )
        )

    #: Set when the database is reached through a transaction pooler — Neon's
    #: `-pooler` endpoint or Railway's PgBouncer. Detected from the host, and
    #: overridable for a pooler whose name does not advertise itself.
    database_pooled_override: bool | None = Field(default=None, alias="DATABASE_POOLED")

    @property
    def database_pooled(self) -> bool:
        if self.database_pooled_override is not None:
            return self.database_pooled_override
        url = self.database_url_override.lower()
        return "-pooler." in url or "pgbouncer" in url

    @property
    def database_requires_ssl(self) -> bool:
        """Whether the supplied URL asked for TLS.

        Hosted Postgres always does. The flag is read here rather than left in
        the URL because asyncpg rejects libpq's `sslmode` parameter — see
        `_as_driver_url`.
        """
        return "sslmode=" in self.database_url_override or "ssl=" in self.database_url_override

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


#: Values that must never reach production. The default ships in the
#: repository, so anything derived from it is public knowledge.
WEAK_SECRETS = frozenset(
    {"dev-only-change-me", "change-me", "secret", "changeme", "test", "development"}
)

MIN_SECRET_BYTES = 32


class InsecureConfiguration(RuntimeError):
    """Raised at startup when a setting would be unsafe in this environment."""


def assert_secret_key_is_strong(config: "Settings") -> None:
    """Refuse to start with a weak signing key outside local development.

    Length alone is not the test. A thirty-two character key that is the
    published default is worse than a short random one, because an attacker
    does not have to guess it — they read it here. Both are checked.

    Local and test are exempt so a fresh clone runs without ceremony; every
    other environment fails loudly at boot rather than serving forgeable
    tokens.
    """
    if config.environment in ("local", "test"):
        return

    problems: list[str] = []
    if len(config.secret_key.encode()) < MIN_SECRET_BYTES:
        problems.append(
            f"SECRET_KEY is {len(config.secret_key.encode())} bytes; "
            f"at least {MIN_SECRET_BYTES} are required"
        )
    if config.secret_key.strip().lower() in WEAK_SECRETS:
        problems.append("SECRET_KEY is a known default value")

    if problems:
        raise InsecureConfiguration(
            "Refusing to start with an unsafe configuration:\n"
            + "\n".join(f"  - {p}" for p in problems)
            + '\n\nGenerate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so configuration is parsed exactly once per process."""
    return Settings()


settings = get_settings()
