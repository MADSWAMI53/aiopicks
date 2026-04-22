"""Utility helpers for the AIOPicks service."""

from __future__ import annotations

import functools
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_SLUG_NON_ALNUM_RE = re.compile(r"[^a-zA-Z0-9]+")
_SLUG_DASH_RE = re.compile(r"-+")


def _extract_first_json_dict(text: str) -> dict[str, Any]:
    """Return the first JSON object (dict) found in a string."""

    if not text:
        raise ValueError("No JSON object found in response")

    start: int | None = None
    depth = 0
    in_string = False
    escape = False

    for index, ch in enumerate(text):
        if start is None:
            if ch == "{":
                start = index
                depth = 1
                in_string = False
                escape = False
            continue

        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth != 0:
                continue
            payload = text[start : index + 1]
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                start = None
                continue
            if isinstance(parsed, dict):
                return parsed
            start = None

    raise ValueError("No JSON object found in response")


@functools.lru_cache(maxsize=4096)
def slugify(value: str) -> str:
    """Return a URL-friendly slug."""

    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = _SLUG_NON_ALNUM_RE.sub("-", value)
    value = value.strip("-")
    value = _SLUG_DASH_RE.sub("-", value)
    return value.lower() or "catalog"


def extract_json_object(content: str) -> dict[str, Any]:
    """Extract and parse the first JSON object from the model response."""

    match = JSON_BLOCK_RE.search(content)
    if match:
        try:
            return _extract_first_json_dict(match.group(1))
        except ValueError:
            pass
    return _extract_first_json_dict(content)


def ensure_unique_meta_id(base_id: str, fallback: str, index: int) -> str:
    """Generate a deterministic unique meta identifier."""

    if base_id:
        return base_id
    slug = slugify(fallback)
    return f"{slug}-{index}"


def ensure_utc_datetime(value: datetime | None) -> datetime | None:
    """Return a timezone-aware UTC datetime (treat naive values as UTC)."""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
