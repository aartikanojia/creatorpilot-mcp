"""
Centralized configuration for the MCP server.

Loads all environment variables and provides typed configuration objects.
No hardcoded secrets - all sensitive values must come from environment.
"""

import os
from typing import Optional
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class RedisConfig:
    """Redis connection configuration for short-term memory."""

    host: str = field(default_factory=lambda: os.getenv(
        "REDIS_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(
        os.getenv("REDIS_PORT", "6379")))
    password: Optional[str] = field(
        default_factory=lambda: os.getenv("REDIS_PASSWORD"))
    db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))
    ssl: bool = field(default_factory=lambda: os.getenv(
        "REDIS_SSL", "false").lower() == "true")

    @property
    def url(self) -> str:
        """Build Redis connection URL."""
        protocol = "rediss" if self.ssl else "redis"
        auth = f":{self.password}@" if self.password else ""
        return f"{protocol}://{auth}{self.host}:{self.port}/{self.db}"


@dataclass
class PostgresConfig:
    """PostgreSQL connection configuration for long-term memory."""

    # Support direct DATABASE_URL or individual components
    database_url: Optional[str] = field(
        default_factory=lambda: os.getenv("DATABASE_URL"))
    host: str = field(default_factory=lambda: os.getenv(
        "POSTGRES_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(
        os.getenv("POSTGRES_PORT", "5432")))
    user: str = field(
        default_factory=lambda: os.getenv("POSTGRES_USER", "creatorpilot_admin"))
    password: Optional[str] = field(
        default_factory=lambda: os.getenv("POSTGRES_PASSWORD"))
    database: str = field(default_factory=lambda: os.getenv(
        "POSTGRES_DB", "creatorpilot"))
    ssl_mode: str = field(default_factory=lambda: os.getenv(
        "POSTGRES_SSL_MODE", "prefer"))

    @property
    def url(self) -> str:
        """
        Build PostgreSQL connection URL.

        Prioritizes DATABASE_URL if set, otherwise builds from components.
        Uses synchronous psycopg2 driver (MCP runs sync SQLAlchemy).
        """
        if self.database_url:
            url = self.database_url
            # Normalize postgres:// to postgresql://
            if url.startswith("postgres://"):
                return url.replace("postgres://", "postgresql://", 1)
            return url

        # Build from individual components
        auth = f"{self.user}:{self.password}@" if self.password else f"{self.user}@"
        return f"postgresql://{auth}{self.host}:{self.port}/{self.database}?sslmode={self.ssl_mode}"


@dataclass
class LLMConfig:
    """LLM provider configuration - supports Azure OpenAI (default) and Gemini (fallback)."""

    provider: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "azure_openai"))
    api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("LLM_API_KEY"))
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4"))
    base_url: Optional[str] = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL"))
    max_tokens: int = field(default_factory=lambda: int(
        os.getenv("LLM_MAX_TOKENS", "4096")))
    temperature: float = field(default_factory=lambda: float(
        os.getenv("LLM_TEMPERATURE", "0.7")))
    timeout: int = field(default_factory=lambda: int(
        os.getenv("LLM_TIMEOUT", "60")))

    # Azure OpenAI configuration
    azure_openai_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_API_KEY"))
    azure_openai_endpoint: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_ENDPOINT"))
    azure_openai_api_version: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"))
    azure_openai_deployment_name: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_DEPLOYMENT"))

    # Gemini configuration (fallback)
    gemini_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    gemini_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-flash-latest"))



@dataclass
class ServerConfig:
    """Server runtime configuration."""

    host: str = field(default_factory=lambda: os.getenv(
        "SERVER_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(
        os.getenv("SERVER_PORT", "8001")))
    debug: bool = field(default_factory=lambda: os.getenv(
        "DEBUG", "false").lower() == "true")
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    cors_origins: list[str] = field(
        default_factory=lambda: os.getenv("CORS_ORIGINS", "*").split(",")
    )


@dataclass
class FlagsConfig:
    """Feature flags for testing and development."""

    force_pro_mode: bool = field(
        default_factory=lambda: os.getenv("FORCE_PRO_MODE", "false").lower() == "true"
    )


@dataclass
class Config:
    """
    Root configuration object aggregating all config sections.

    Usage:
        config = Config()
        redis_url = config.redis.url
        llm_model = config.llm.model
    """

    redis: RedisConfig = field(default_factory=RedisConfig)
    postgres: PostgresConfig = field(default_factory=PostgresConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    flags: FlagsConfig = field(default_factory=FlagsConfig)

    def validate(self) -> list[str]:
        """
        Validate configuration and return list of warnings/errors.

        Returns:
            List of validation messages (empty if all valid)
        """
        warnings = []

        if not self.llm.azure_openai_api_key and not self.llm.gemini_api_key and not self.llm.api_key:
            warnings.append("No LLM API key set (Azure OpenAI or Gemini) - LLM calls will fail")

        if not self.redis.password and not self.server.debug:
            warnings.append("REDIS_PASSWORD not set in production mode")

        if not self.postgres.password and not self.server.debug:
            warnings.append("POSTGRES_PASSWORD not set in production mode")

        return warnings


# Global config instance - import and use this
config = Config()
