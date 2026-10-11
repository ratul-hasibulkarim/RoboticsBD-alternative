"""Runtime configuration. Every secret comes from the environment and is validated at boot."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    env: str = Field(default="dev", pattern=r"^(dev|test|prod)$")

    database_url: str = "postgresql+asyncpg://voltfind:voltfind@localhost:5432/voltfind"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"

    typesense_host: str = "localhost"
    typesense_port: int = 8108
    typesense_protocol: str = "http"
    typesense_api_key: SecretStr = SecretStr("voltfind-dev-key")

    s3_endpoint: str = "http://localhost:9000"
    s3_bucket_raw: str = "voltfind-raw"
    s3_access_key: SecretStr = SecretStr("minioadmin")
    s3_secret_key: SecretStr = SecretStr("minioadmin")

    # Signing key for magic-link tokens and session hashes.
    secret_key: SecretStr = SecretStr("dev-only-secret-change-me-0123456789abcdef")
    # Comma-separated SHA-256 hex digests of admin bearer tokens.
    admin_token_sha256: str = ""

    sources_file: Path = REPO_ROOT / "crawler" / "sources.yaml"

    # LLM extraction (stage B). Empty base URL disables the stage.
    llm_base_url: str = ""
    llm_model: str = "llama3.1:8b"
    llm_api_key: SecretStr = SecretStr("")
    llm_daily_budget_usd: float = 5.0
    llm_cost_per_1k_tokens_usd: float = 0.0
    llm_min_confidence: float = 0.85

    # FX
    fx_provider_url: str = "https://open.er-api.com/v6/latest/USD"

    # Distributor/API keys (empty = client refuses to run).
    mouser_api_key: SecretStr = SecretStr("")
    digikey_client_id: SecretStr = SecretStr("")
    digikey_client_secret: SecretStr = SecretStr("")
    lcsc_api_key: SecretStr = SecretStr("")
    lcsc_api_secret: SecretStr = SecretStr("")
    youtube_api_key: SecretStr = SecretStr("")
    github_token: SecretStr = SecretStr("")
    reddit_client_id: SecretStr = SecretStr("")
    reddit_client_secret: SecretStr = SecretStr("")

    # Embeddings
    embedding_backend: str = Field(default="hashing", pattern=r"^(hashing|sentence-transformers)$")
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_sender: str = "VoltFind <alerts@voltfind.com>"
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")

    public_site_url: str = "http://localhost:3000"
    web_revalidate_url: str = "http://localhost:3000/api/revalidate"
    web_revalidate_secret: SecretStr = SecretStr("dev-revalidate-secret")

    api_rate_limit_per_minute: int = 120
    search_cache_ttl_s: int = 300

    @field_validator("secret_key")
    @classmethod
    def _secret_strength(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    def admin_token_hashes(self) -> frozenset[str]:
        return frozenset(h.strip().lower() for h in self.admin_token_sha256.split(",") if h.strip())

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "+psycopg")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    if s.env == "prod" and s.secret_key.get_secret_value().startswith("dev-only"):
        raise RuntimeError("SECRET_KEY must be set in production")
    return s
