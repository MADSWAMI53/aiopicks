"""Integration helpers for Ollama (local inference).

This client mirrors the interface of OpenAIClient so the generator can
switch engines by mode without branching call sites. Ollama exposes an
OpenAI-compatible /api/chat endpoint, so the structure is basically the same
except that no API key is required and the base URL points to the local
Ollama server.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Sequence

import httpx
from pydantic import ValidationError

from ..config import Settings
from ..models import Catalog, CatalogBundle, CatalogItem
from ..stable_catalogs import STABLE_CATALOGS, StableCatalogDefinition
from ..utils import extract_json_object

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are AIOPicks, an AI that curates playful but trustworthy movie and series catalogs "
    "for the Stremio media center. You always respond with a single JSON object that matches "
    "the documented schema and never include commentary outside JSON."
)


class OllamaClient:
    """Client responsible for talking to a local Ollama instance."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self._settings = settings
        self._client = http_client

    async def generate_catalogs(
        self,
        summary: dict[str, Any],
        *,
        seed: str,
        api_key: str | None = None,  # unused — kept for interface compatibility
        model: str | None = None,
        exclusions: dict[str, dict[str, Any]] | None = None,
        retry_limit: int | None = None,
        definitions: Sequence[StableCatalogDefinition] | None = None,
    ) -> CatalogBundle:
        item_target = summary.get(
            "catalog_item_count", self._settings.catalog_item_count
        )
        resolved_model = model or self._settings.ollama_model

        lane_definitions: tuple[StableCatalogDefinition, ...] = tuple(
            definitions or STABLE_CATALOGS
        )
        if not lane_definitions:
            raise RuntimeError("No catalog definitions configured")

        # Ollama runs locally so parallelising all lanes at once can saturate
        # the GPU. Run in smaller batches to keep it responsive.
        batch_size = 1
        movie_catalogs: list[Catalog] = []
        series_catalogs: list[Catalog] = []

        for batch_start in range(0, len(lane_definitions), batch_size):
            batch = lane_definitions[batch_start : batch_start + batch_size]
            tasks = [
                asyncio.create_task(
                    self._generate_catalog_for_definition(
                        summary,
                        definition,
                        item_target=item_target,
                        seed=f"{seed}-{batch_start + index:02d}",
                        model=resolved_model,
                    )
                )
                for index, definition in enumerate(batch)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for definition, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.warning(
                        "Ollama generation failed for lane %s: %s",
                        definition.key,
                        result,
                    )
                    continue
                if result is None:
                    continue
                if definition.content_type == "movie":
                    movie_catalogs.append(result)
                else:
                    series_catalogs.append(result)

        bundle = CatalogBundle(
            movie_catalogs=movie_catalogs, series_catalogs=series_catalogs
        )
        if bundle.is_empty():
            raise RuntimeError("Ollama returned an empty catalog bundle")
        return bundle

    async def _generate_catalog_for_definition(
        self,
        summary: dict[str, Any],
        definition: StableCatalogDefinition,
        *,
        item_target: int,
        seed: str,
        model: str,
    ) -> Catalog | None:
        profile = summary.get("profile", {}) or {}
        movie_profile = profile.get("movies", {}) or {}
        series_profile = profile.get("series", {}) or {}
        content_label = "movie" if definition.content_type == "movie" else "series"
        content_label_plural = "movies" if content_label == "movie" else "series"

        prompt_lines = [
            "You are the trusted cinephile friend helping a power user discover new titles based on their Trakt history.",
            f'This request focuses on the "{definition.title}" lane for {content_label_plural}.',
            f"Random seed: {seed}.",
            f"Recommend EXACTLY {item_target} {content_label_plural}.",
            'Respond strictly with JSON: {"items":[{"title":"","type":"'
            + definition.content_type
            + '","year":2024,"description":""}]}',
        ]
        taste_bits: list[str] = []
        if movie_profile.get("taste_summary") and definition.content_type == "movie":
            taste_bits.append(str(movie_profile["taste_summary"]))
        if series_profile.get("taste_summary") and definition.content_type == "series":
            taste_bits.append(str(series_profile["taste_summary"]))
        if taste_bits:
            prompt_lines.append("Keep aligned with taste: " + "; ".join(taste_bits))
        prompt = "\n".join(prompt_lines)

        request_payload = {
            "model": model,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "top_p": 1.0,
                # Ollama uses num_predict instead of max_tokens
                "num_predict": max(2000, min(12000, 900 + int(item_target) * 20)),
            },
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }

        try:
            response = await self._client.post(
                "/api/chat",
                json=request_payload,
                # Local inference can be slow; give it plenty of time
                timeout=httpx.Timeout(300.0, connect=5.0),
            )
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Could not connect to Ollama at {self._client.base_url}. "
                "Is Ollama running? (ollama serve)"
            ) from exc

        if response.status_code >= 400:
            raise RuntimeError(
                f"Ollama returned HTTP {response.status_code}: {response.text}"
            )

        data = response.json()
        # Ollama's OpenAI-compatible endpoint returns {"message": {"content": ...}}
        message = data.get("message", {})
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            return None

        parsed = extract_json_object(content)
        raw_items: list[dict[str, Any]] = []
        if isinstance(parsed, dict):
            candidate = parsed.get("items")
            if isinstance(candidate, list):
                raw_items = [entry for entry in candidate if isinstance(entry, dict)]
        elif isinstance(parsed, list):
            raw_items = [entry for entry in parsed if isinstance(entry, dict)]

        items: list[CatalogItem] = []
        for entry in raw_items:
            item_data = {**entry, "type": definition.content_type}
            try:
                item = CatalogItem.model_validate(item_data)
            except ValidationError:
                continue
            items.append(item)

        return Catalog(
            id=f"aiopicks-{definition.content_type}-{definition.key}",
            type=definition.content_type,
            title=definition.title,
            description=definition.description,
            seed=seed,
            items=items,
            generated_at=datetime.now(timezone.utc),
        )