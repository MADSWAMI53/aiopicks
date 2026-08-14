"""Application configuration models."""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable, Literal

from pydantic import AliasChoices, Field, HttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .stable_catalogs import (
    STABLE_CATALOGS,
    STABLE_CATALOG_COUNT,
    StableCatalogDefinition,
)


DEFAULT_CATALOG_KEYS: tuple[str, ...] = tuple(
    definition.key for definition in STABLE_CATALOGS
)


class Settings(BaseSettings):
    """Settings loaded from environment variables or a .env file."""

    app_name: str = Field(default="AIOPicks", alias="APP_NAME")
    server_host: str = Field(default="0.0.0.0", alias="HOST")
    server_port: int = Field(default=3000, alias="PORT")

    trakt_client_id: str | None = Field(default=None, alias="TRAKT_CLIENT_ID")
    trakt_client_secret: str | None = Field(
        default=None, alias="TRAKT_CLIENT_SECRET"
    )
    trakt_access_token: str | None = Field(default=None, alias="TRAKT_ACCESS_TOKEN")
    trakt_redirect_uri: HttpUrl | None = Field(
        default=None, alias="TRAKT_REDIRECT_URI"
    )
    trakt_history_limit: int = Field(
        default=0, alias="TRAKT_HISTORY_LIMIT", ge=0, le=10_000
    )
    trakt_history_cache_ttl_seconds: int = Field(
        default=0,
        alias="TRAKT_HISTORY_CACHE_TTL_SECONDS",
        ge=0,
        description=(
            "Cache compacted Trakt history per profile/type for this many seconds. "
            "0 disables caching."
        ),
    )

    simkl_client_id: str | None = Field(default=None, alias="SIMKL_CLIENT_ID")
    simkl_client_secret: str | None = Field(
        default=None, alias="SIMKL_CLIENT_SECRET"
    )
    simkl_access_token: str | None = Field(default=None, alias="SIMKL_ACCESS_TOKEN")
    simkl_redirect_uri: HttpUrl | None = Field(
        default=None, alias="SIMKL_REDIRECT_URI"
    )
    simkl_history_limit: int = Field(
        default=0, alias="SIMKL_HISTORY_LIMIT", ge=0, le=10_000
    )
    simkl_history_cache_ttl_seconds: int = Field(
        default=0,
        alias="SIMKL_HISTORY_CACHE_TTL_SECONDS",
        ge=0,
        description=(
            "Cache compacted Simkl history per profile/type for this many seconds. "
            "0 disables caching."
        ),
    )

    openrouter_api_key: str | None = Field(
        default=None, alias="OPENROUTER_API_KEY"
    )
    openrouter_model: str = Field(
        default="google/gemini-2.5-flash-lite", alias="OPENROUTER_MODEL"
    )

    # Discovery engine selection: "openrouter", "openai", or "local"
    generator_mode: Literal["openrouter", "openai", "ollama","local"] = Field(
        default="local", alias="GENERATOR_MODE"
    )

    catalog_keys: tuple[str, ...] = Field(
        default=DEFAULT_CATALOG_KEYS,
        alias="CATALOG_KEYS",
    )
    catalog_count: int = Field(
        default=STABLE_CATALOG_COUNT,
        alias="CATALOG_COUNT",
        ge=1,
        le=STABLE_CATALOG_COUNT,
    )
    catalog_item_count: int = Field(
        default=8, alias="CATALOG_ITEM_COUNT", ge=1, le=100
    )
    refresh_interval_seconds: int = Field(
        default=43_200, alias="REFRESH_INTERVAL", ge=3_600
    )
    response_cache_seconds: int = Field(
        default=1_800, alias="CACHE_TTL", ge=300
    )

    generation_retry_limit: int = Field(
        default=3, alias="GENERATION_RETRY_LIMIT", ge=0, le=50
    )

    trakt_api_url: HttpUrl = Field(
        default="https://api.trakt.tv", alias="TRAKT_API_URL"
    )
    trakt_authorize_url: HttpUrl = Field(
        default="https://trakt.tv/oauth/authorize", alias="TRAKT_AUTHORIZE_URL"
    )
    simkl_api_url: HttpUrl = Field(
        default="https://api.simkl.com", alias="SIMKL_API_URL"
    )
    simkl_authorize_url: HttpUrl = Field(
        default="https://simkl.com/oauth/authorize", alias="SIMKL_AUTHORIZE_URL"
    )
    simkl_token_url: HttpUrl = Field(
        default="https://api.simkl.com/oauth/token", alias="SIMKL_TOKEN_URL"
    )
    openrouter_api_url: HttpUrl = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_API_URL"
    )
    # OpenAI (direct) configuration
    openai_api_key: str | None = Field(
        default=None, alias="OPENAI_API_KEY"
    )
    openai_model: str = Field(
        default="gpt-5-mini-2025-08-07", alias="OPENAI_MODEL"
    )
    openai_api_url: HttpUrl = Field(
        default="https://api.openai.com/v1", alias="OPENAI_API_URL"
    )
    ollama_model: str = Field(
    default="mistral:7b-instruct-q4_K_M", alias="OLLAMA_MODEL"
    )
    ollama_api_url: HttpUrl = Field(
        default="https://llm.elijahb5088.cc", alias="OLLAMA_API_URL"
    )
    metadata_addon_url: HttpUrl | None = Field(
        default=None,
        alias="METADATA_ADDON_URL",
        validation_alias=AliasChoices("METADATA_ADDON_URL", "CINEMETA_API_URL"),
    )

    database_url: str = Field(
        default="sqlite+aiosqlite:///./aiopicks.db", alias="DATABASE_URL"
    )

    environment: Literal["development", "production"] = Field(
        default="development", alias="ENVIRONMENT"
    )

    @field_validator("catalog_keys", mode="before")
    @classmethod
    def _parse_catalog_keys(cls, value: object) -> tuple[str, ...]:
        """Normalise catalog key selections from environment values."""

        if value is None:
            return DEFAULT_CATALOG_KEYS
        if isinstance(value, str):
            raw_values = [part.strip() for part in value.split(",")]
        elif isinstance(value, Iterable):
            raw_values = [str(part).strip() for part in value]
        else:
            raise TypeError("CATALOG_KEYS must be a string or iterable of strings")

        cleaned: list[str] = []
        for entry in raw_values:
            if not entry:
                continue
            slug = entry.replace("_", "-").replace(" ", "-").lower()
            slug = "-".join(filter(None, slug.split("-")))
            if not slug:
                continue
            if slug not in DEFAULT_CATALOG_KEYS:
                raise ValueError("Unknown catalog keys configured")
            if slug not in cleaned:
                cleaned.append(slug)
        if not cleaned:
            return DEFAULT_CATALOG_KEYS
        return tuple(cleaned)

    @model_validator(mode="before")
    @classmethod
    def _validate_catalog_count(cls, data: object) -> object:
        """Reject explicit catalog counts that disagree with the configured keys."""

        if not isinstance(data, dict):
            return data

        supplied_count = data.get("CATALOG_COUNT", data.get("catalog_count"))
        if supplied_count is None:
            return data

        keys_value = data.get("CATALOG_KEYS", data.get("catalog_keys"))
        if keys_value is None:
            return data

        if isinstance(keys_value, str):
            values = [part.strip() for part in keys_value.split(",")]
        elif isinstance(keys_value, Iterable):
            values = [str(part).strip() for part in keys_value]
        else:
            values = [str(keys_value).strip()]

        normalized: list[str] = []
        for entry in values:
            if not entry:
                continue
            slug = entry.replace("_", "-").replace(" ", "-").lower()
            slug = "-".join(filter(None, slug.split("-")))
            if slug:
                normalized.append(slug)

        if len(normalized) != int(supplied_count):
            raise ValueError(
                "Catalog count must match the number of configured catalog keys"
            )
        return data

    @model_validator(mode="after")
    def _sync_catalog_configuration(self) -> "Settings":
        """Keep the catalog count aligned with the selected catalog keys."""

        self.catalog_count = len(self.catalog_keys)
        return self

    @property
    def catalog_definitions(self) -> tuple[StableCatalogDefinition, ...]:
        """Return ordered catalog lane definitions for the selected keys."""

        definition_map = {definition.key: definition for definition in STABLE_CATALOGS}
        return tuple(definition_map[key] for key in self.catalog_keys)

    @property
    def cinemeta_api_url(self) -> HttpUrl | None:
        """Maintain backwards compatibility with the previous setting name."""

        return self.metadata_addon_url

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()  # type: ignore[call-arg]


settings = get_settings()
