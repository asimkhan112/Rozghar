"""Application configuration.

Every setting is typed and read from the environment. Missing required values
raise at import time rather than at first use, so a misconfigured deployment
fails on startup instead of on the first request that happens to need them.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- application -----------------------------------------------------
    app_name: str = "Rozgar API"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # --- database --------------------------------------------------------
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
    #: Populated in Milestone 2. Declared here so configuration has one home.
    secret_key: str = Field(default="dev-only-change-me", min_length=8)
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

    # --- startup ---------------------------------------------------------
    #: When true, a mismatch between the Permission enum and the permissions
    #: table aborts startup. Disabled only for the migration that seeds them.
    validate_permissions_on_startup: bool = True

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Async driver URL, used by the application at runtime."""
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

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so configuration is parsed exactly once per process."""
    return Settings()


settings = get_settings()
