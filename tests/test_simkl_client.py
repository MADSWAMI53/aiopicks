"""Tests for the Simkl API client helpers."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from app.config import Settings
from app.main import _post_simkl_oauth
from app.services.simkl import SimklClient


@pytest.fixture
def anyio_backend() -> str:
    """Force AnyIO tests to run on asyncio without requiring trio."""
    return "asyncio"


def build_settings(**overrides: Any) -> Settings:
    """Return a settings object with defaults suitable for tests."""
    base = {
        "SIMKL_CLIENT_ID": "simkl-client-id",
        "SIMKL_ACCESS_TOKEN": "simkl-access-token",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.mark.anyio("asyncio")
async def test_fetch_history_paginates_until_limit() -> None:
    """The client should follow Simkl pagination to satisfy the requested limit."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = int(request.url.params.get("page", "1"))
        limit = int(request.url.params.get("limit", "0"))
        if page > 2:
            return httpx.Response(
                200,
                json=[],
                headers={"x-pagination-item-count": "150", "x-pagination-page-count": "2"},
            )
        start = (page - 1) * 100
        items = [
            {
                "id": start + index + 1,
                "watched_at": "2024-01-01T00:00:00.000Z",
                "type": "movie",
                "movie": {
                    "title": f"Movie {start + index + 1}",
                    "year": 2000,
                    "ids": {"imdb": f"tt{start + index + 1:07d}", "simkl": start + index + 1},
                },
            }
            for index in range(limit)
        ]
        return httpx.Response(
            200,
            json=items,
            headers={"x-pagination-item-count": "150", "x-pagination-page-count": "2"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.example.com") as http_client:
        client = SimklClient(build_settings(), http_client)
        batch = await client.fetch_history("movies", limit=120)

    assert batch.fetched is True
    assert len(batch.items) == 120
    assert batch.total == 150
    assert requests[0].url.params["limit"] == "100"
    assert requests[1].url.params["limit"] == "20"
    assert len(requests) == 2


@pytest.mark.anyio("asyncio")
async def test_fetch_history_handles_error_response() -> None:
    """HTTP failures should result in an empty history payload."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.example.com") as http_client:
        client = SimklClient(build_settings(), http_client)
        batch = await client.fetch_history("movies", limit=50)

    assert batch.fetched is False
    assert batch.items == []
    assert batch.total == 0


@pytest.mark.anyio("asyncio")
async def test_post_simkl_oauth_uses_form_encoded_payload() -> None:
    """Simkl token exchange should send OAuth data as form fields, not JSON."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = parse_qs(request.content.decode("utf-8"))
        assert request.headers.get("Content-Type", "").startswith(
            "application/x-www-form-urlencoded"
        )
        assert body["code"] == ["auth-code"]
        assert body["client_id"] == ["simkl-client-id"]
        assert body["client_secret"] == ["simkl-client-secret"]
        assert body["grant_type"] == ["authorization_code"]
        return httpx.Response(200, json={"access_token": "simkl-token"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.example.com") as client:
        response = await _post_simkl_oauth(
            "https://api.example.com/oauth/token",
            {
                "code": "auth-code",
                "client_id": "simkl-client-id",
                "client_secret": "simkl-client-secret",
                "redirect_uri": "http://localhost:3000/api/simkl/callback",
                "grant_type": "authorization_code",
            },
            client=client,
        )

    assert response.status_code == 200
    assert response.json()["access_token"] == "simkl-token"
