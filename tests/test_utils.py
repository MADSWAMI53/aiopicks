from datetime import datetime, timedelta, timezone

from app.utils import ensure_unique_meta_id, ensure_utc_datetime, extract_json_object, slugify


def test_slugify_basic():
    assert slugify("Late Night Thrills!") == "late-night-thrills"


def test_extract_json_object_from_markdown():
    payload = """
    Here is your payload:
    ```json
    {"movie_catalogs": []}
    ```
    """
    assert extract_json_object(payload) == {"movie_catalogs": []}


def test_ensure_unique_meta_id_with_fallback():
    meta_id = ensure_unique_meta_id("", "Some Title", 3)
    assert meta_id.startswith("some-title")


def test_ensure_utc_datetime_attaches_utc_to_naive() -> None:
    naive = datetime(2026, 1, 1, 12, 0, 0)
    coerced = ensure_utc_datetime(naive)
    assert coerced is not None
    assert coerced.tzinfo == timezone.utc
    assert coerced.replace(tzinfo=None) == naive


def test_ensure_utc_datetime_converts_offset_to_utc() -> None:
    eastern = timezone(timedelta(hours=-5))
    value = datetime(2026, 1, 1, 12, 0, 0, tzinfo=eastern)
    coerced = ensure_utc_datetime(value)
    assert coerced is not None
    assert coerced.tzinfo == timezone.utc
    assert coerced.hour == 17
