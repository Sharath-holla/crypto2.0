from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv(override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    isolated_test_environment: bool = False
    isolated_postgres_ci: bool = False
    fixture_catalog_enabled: bool = False
    ai_spending_mode: Literal["ZERO_COST_ONLY"] = "ZERO_COST_ONLY"
    database_url: str = "sqlite:///./data/company.db"
    required_database_backend: Literal["sqlite", "postgresql"] | None = None
    jwt_secret: str = ""
    owner_email: str = "owner@local.test"
    owner_password: str = ""
    web_origin: str = "http://localhost:3000"
    mock_enabled: bool = True
    execution_enabled: bool = False
    pdf_upload_limit: int = Field(default=1048576, ge=1024, le=1048576)
    pdf_page_limit: int = Field(default=50, ge=1, le=100)
    pdf_timeout_seconds: int = Field(default=5, ge=1, le=10)
    runner_url: str = "http://127.0.0.1:8090"
    runner_token: str = ""
    github_publication_token_env: str = "AIVENTRA_GITHUB_TOKEN"
    github_publication_repositories: str = ""
    delivery_release_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    client_invitation_ttl_seconds: int = Field(default=172800, ge=60, le=604800)
    artifact_root: Path = Path("artifacts")
    repository_root: Path = Path("data/repositories")
    provider_allowed_hosts: str = "api.openai.com,api.anthropic.com,generativelanguage.googleapis.com,api.x.ai,api.deepseek.com,localhost,127.0.0.1"
    research_allowed_hosts: str = "cloud.google.com,lightning.ai,aws.amazon.com,azure.microsoft.com"
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    s3_bucket: str = ""
    s3_endpoint: str = ""
    provider_secret_key: str = ""
    embedding_provider: str = Field(
        default="fastembed", pattern="^(disabled|fastembed|ollama|deterministic_test)$"
    )
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache: Path = Path("data/embeddings")
    embedding_endpoint: str = "http://127.0.0.1:11434"
    memory_context_chars: int = Field(default=12000, ge=1000, le=24000)
    scheduler_concurrency: int = Field(default=4, ge=1, le=16)
    ollama_context_tokens: int = Field(default=8192, ge=2048, le=32768)
    ollama_thinking: bool = False
    ollama_min_available_memory_mb: int = Field(default=0, ge=0, le=65536)
    ollama_keep_alive_seconds: int = Field(default=0, ge=0, le=300)
    ollama_read_timeout_seconds: int = Field(default=120, ge=5, le=300)
    ollama_request_timeout_seconds: int = Field(default=180, ge=10, le=600)
    login_window_seconds: int = Field(ge=10, le=3600, default=60)
    login_account_limit: int = Field(ge=1, le=100, default=10)
    login_source_limit: int = Field(ge=1, le=10000, default=100)
    worker_stale_seconds: int = Field(ge=15, le=600, default=90)
    crypto_adapter_url: str = "http://127.0.0.1:8011"
    crypto_adapter_token: str = ""
    crypto_project_org_id: str = ""

    def validate_startup(self) -> None:
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must have at least 32 characters. Run bootstrap first.")
        if self.app_env == "production" and (self.mock_enabled or not self.oidc_issuer):
            raise ValueError("Production requires OIDC and MOCK_ENABLED=false.")


@lru_cache
def settings() -> Settings:
    return Settings()
