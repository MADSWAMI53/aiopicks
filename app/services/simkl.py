"""Utilities for communicating with the Simkl API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HistoryBatch:
    """Container for a page of history items and the reported total size."""

    items: list[dict[str, Any]]
    total: int = 0
    fetched: bool = True


class SimklClient:
    """Thin wrapper around the Simkl HTTP API."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self._settings = settings
        self._client = http_client
        self._max_retries = 3

    def _headers(
        self,
        *,
        access_token: str | None = None,
    ) -> dict[str, str]:
        headers = {
            "User-Agent": f"{self._settings.app_name} (aiopicks)",
            "accept": "application/json",
        }
        resolved_access_token = access_token or self._settings.simkl_access_token
        if resolved_access_token:
            headers["Authorization"] = f"Bearer {resolved_access_token}"
        resolved_client_id = self._settings.simkl_client_id
        if resolved_client_id:
            headers["simkl-api-key"] = resolved_client_id
        return headers

    async def fetch_user(
        self,
        *,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        """Fetch the authenticated Simkl user profile."""
        resolved_access_token = access_token or self._settings.simkl_access_token
        if not resolved_access_token:
            logger.info("Simkl credentials missing, returning empty user")
            return {}

        try:
            response = await self._client.get(
                "/users/settings",
                headers=self._headers(access_token=resolved_access_token),
            )
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch Simkl user: %s", exc)
            return {}

            if response.status_code == 401:
                logger.warning("Simkl returned 401 Unauthorized for user fetch; access token may be invalid or expired.")
                return {}
            if 400 <= response.status_code < 500:
                logger.warning("Simkl 4xx during user fetch: %s %s", response.status_code, response.text[:200])
                return {}
            if 500 <= response.status_code < 600:
                logger.warning("Failed to fetch Simkl user: %s", response.text)
                return {}

        try:
            data = response.json()
        except ValueError:
            return {}
        if not isinstance(data, Mapping):
            return {}
        return dict(data)

    async def fetch_history(
        self,
        content_type: str,
        *,
        access_token: str | None = None,
        limit: int | None = None,
    ) -> HistoryBatch:
        """Fetch the user's watching history for movies or shows."""
        resolved_access_token = access_token or self._settings.simkl_access_token
        if not resolved_access_token:
            logger.info("Simkl credentials missing, returning empty history for %s", content_type)
            return HistoryBatch(items=[], total=0, fetched=False)

        target = limit if limit is not None else self._settings.simkl_history_limit
        try:
            parsed_limit = int(target) if target is not None else None
        except (TypeError, ValueError):
            parsed_limit = int(self._settings.simkl_history_limit)
        if parsed_limit is not None and parsed_limit <= 0:
            parsed_limit = None

        collected: list[dict[str, Any]] = []
        total = 0
        page = 1
        page_size = 100
        remaining = parsed_limit

        while True:
            page_limit = page_size if remaining is None else min(remaining, page_size)
            if page_limit <= 0:
                break

            params: dict[str, Any] = {
                "extended": "full",
                "limit": page_limit,
                "page": page,
            }

            try:
                response = await self._client.get(
                    f"/sync/history/{content_type}",
                    headers=self._headers(access_token=resolved_access_token),
                    params=params,
                )
            except httpx.HTTPError as exc:
                logger.warning("Failed to fetch Simkl history for %s (page %s): %s", content_type, page, exc)
                return HistoryBatch(items=collected, total=total or len(collected), fetched=False)

            if response.status_code == 401:
                logger.warning("Simkl returned 401 Unauthorized for %s history; access token may be invalid or expired.", content_type)
                return HistoryBatch(items=collected, total=total or len(collected), fetched=False)
            if 400 <= response.status_code < 500:
                logger.warning("Simkl 4xx during history fetch for %s (page %s): %s %s", content_type, page, response.status_code, response.text[:200])
                return HistoryBatch(items=collected, total=total or len(collected), fetched=False)
            if 500 <= response.status_code < 600:
                logger.warning("Simkl 5xx during history fetch for %s: %s", content_type, response.text)
                return HistoryBatch(items=collected, total=total or len(collected), fetched=False)

            try:
                payload = response.json()
            except ValueError:
                logger.warning("Unexpected non-JSON Simkl response for %s history", content_type)
                return HistoryBatch(items=collected, total=total or len(collected), fetched=False)

            if not isinstance(payload, list):
                logger.warning("Unexpected Simkl response structure for %s", content_type)
                return HistoryBatch(items=[], total=0, fetched=False)

            if total == 0:
                total_header = response.headers.get("x-pagination-item-count")
                if total_header is not None:
                    try:
                        total = int(total_header)
                    except (TypeError, ValueError):
                        total = len(payload)
                else:
                    total = len(payload)

            if not payload:
                break

            collected.extend(payload)
            if remaining is not None:
                remaining -= len(payload)
                if remaining <= 0:
                    break
            if len(payload) < page_limit:
                break
            page += 1
            await asyncio.sleep(0.1)

        if parsed_limit is not None and len(collected) > parsed_limit:
            collected = collected[:parsed_limit]

        return HistoryBatch(items=collected, total=total or len(collected), fetched=True)

    async def fetch_stats(
        self,
        *,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        """Fetch aggregate watch statistics for the authenticated user."""
        resolved_access_token = access_token or self._settings.simkl_access_token
        if not resolved_access_token:
            logger.info("Simkl credentials missing, returning empty stats")
            return {}

        try:
            response = await self._client.get(
                "/users/me/stats",
                headers=self._headers(access_token=resolved_access_token),
            )
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch Simkl stats: %s", exc)
            return {}

        if response.status_code == 401:
            logger.warning("Simkl returned 401 Unauthorized for stats fetch; access token may be invalid or expired.")
            return {}
        if 400 <= response.status_code < 500:
            logger.warning("Simkl 4xx during stats fetch: %s %s", response.status_code, response.text[:200])
            return {}
        if 500 <= response.status_code < 600:
            logger.warning("Failed to fetch Simkl stats: %s", response.text)
            return {}
            logger.warning("Failed to fetch Simkl stats: %s", response.text)
            return {}

        try:
            data = response.json()
        except ValueError:
            return {}
        if not isinstance(data, dict):
            logger.warning("Unexpected Simkl stats response structure")
            return {}
        return data
