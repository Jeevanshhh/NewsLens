"""Application configuration.

All secrets (news provider API keys, JWT secret, DB URL) are read from
environment variables / the git-ignored `.env` file. Nothing sensitive is
hard-coded here. The defaults below are intentionally non-functional
placeholders so the app can boot in development without leaking secrets.

Copy `.env.example` -> `.env` and fill in real values. The API keys that
were previously embedded in the source notebook are treated as COMPROMISED
and must be rotated at the provider dashboards before production use.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel defaults that clearly indicate "not configured".
_UNSET = "your_gnews_api_key_here"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App ----
    app_name: str = "NewsLens API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # ---- Observability ----
    # Emit structured JSON logs. Forced on automatically when ``is_production``.
    log_json: bool = Field(default=False, alias="LOG_JSON")
    # Optional error-monitoring sink (e.g. Sentry). Empty => disabled; the SDK
    # is only imported/initialised when a DSN is present and installed.
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")

    # ---- CORS ----
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    # ---- Auth / JWT ----
    secret_key: str = Field(default="change_me_to_a_long_random_secret", alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    # ---- Account lifecycle / security ----
    password_reset_expire_minutes: int = Field(default=30, alias="PASSWORD_RESET_EXPIRE_MINUTES")
    # Sliding-window brute-force protection on the login endpoint.
    login_max_attempts: int = Field(default=10, alias="LOGIN_MAX_ATTEMPTS")
    login_window_seconds: int = Field(default=300, alias="LOGIN_WINDOW_SECONDS")
    # Reject oversized request bodies (defence-in-depth; auth/search bodies are tiny).
    max_body_bytes: int = Field(default=1_000_000, alias="MAX_BODY_BYTES")

    # ---- Outbound email (password-reset links) ----
    # Left unset in development, reset emails are captured in an in-memory
    # outbox (see email_service) instead of being sent, so nothing is faked.
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")
    smtp_tls: bool = Field(default=True, alias="SMTP_TLS")
    # Absolute URL of the web app, used to build reset links in emails.
    public_frontend_url: str = Field(default="http://localhost:5173", alias="PUBLIC_FRONTEND_URL")

    # ---- Database ----
    database_url: str = Field(default="sqlite:///./newslens.db", alias="DATABASE_URL")

    # ---- News provider keys (placeholders only) ----
    gnews_api_key: str = Field(default=_UNSET, alias="GNEWS_API_KEY")
    newsdata_api_key: str = Field(default="your_newsdata_api_key_here", alias="NEWSDATA_API_KEY")

    # ---- Collection tuning (non-secret) ----
    max_results: int = Field(default=10, alias="MAX_RESULTS")
    request_delay: int = Field(default=1, alias="REQUEST_DELAY")
    rss_country: str = Field(default="IN", alias="RSS_COUNTRY")
    rss_language: str = Field(default="en", alias="RSS_LANGUAGE")

    # ---- Classification ----
    # When enabled, articles the rule-based domain classifier cannot place
    # ("Other") are given a general news topic by a small supervised model, so
    # real headlines stop showing up as "Other" in analytics. Deterministic
    # offline tests turn this off (see tests/conftest) to keep counts stable.
    enable_topic_model: bool = Field(default=True, alias="ENABLE_TOPIC_MODEL")

    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return v.strip()

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    @property
    def gnews_configured(self) -> bool:
        return bool(self.gnews_api_key) and self.gnews_api_key != _UNSET

    @property
    def newsdata_configured(self) -> bool:
        key = self.newsdata_api_key
        return bool(key) and key != "your_newsdata_api_key_here"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def is_postgres(self) -> bool:
        """True when DATABASE_URL targets PostgreSQL (incl. Supabase)."""
        url = self.database_url.lower()
        return url.startswith("postgresql") or url.startswith("postgres")

    @property
    def uses_default_secret(self) -> bool:
        return self.secret_key == "change_me_to_a_long_random_secret"

    def production_safety_errors(self) -> list[str]:
        """Fatal misconfigurations that must prevent a production boot.

        Returned (not raised) so the caller can decide how to fail. Only applied
        when :attr:`is_production` - development keeps its permissive defaults.
        """
        errors: list[str] = []
        if self.uses_default_secret:
            errors.append("SECRET_KEY is still the insecure default value.")
        origins = self.cors_origin_list
        if "*" in origins:
            errors.append("CORS_ORIGINS cannot include '*' when credentials are enabled.")
        if not origins or all(o.endswith(("localhost:5173", "localhost:3000")) for o in origins):
            errors.append("CORS_ORIGINS must be set to explicit production origins.")
        return errors

    def unsafe_default_warnings(self) -> list[str]:
        """Return warnings for still-using insecure default values."""
        warnings: list[str] = []
        if self.secret_key == "change_me_to_a_long_random_secret":
            warnings.append("SECRET_KEY is still the insecure default value.")
        return warnings


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (import-safe, single instance per process)."""
    return Settings()
