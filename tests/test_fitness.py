import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import HevyError
from app.services.hevy import client as client_module
from app.services.hevy import snapshot as snapshot_module
from app.services.hevy.client import HevyClient
from app.services.hevy.derive import (
    build_heatmap,
    build_records,
    format_count,
    format_tonnes,
    title_case,
)
from app.services.hevy.sample import (
    sample_exercise_templates,
    sample_routines,
    sample_workouts,
)
from app.services.hevy.snapshot import HevySnapshotService

UTC_TZ = ZoneInfo("UTC")


@pytest.fixture(autouse=True)
def _reset_hevy_cache() -> None:
    snapshot_module.reset_cache()
    client_module.reset_caches()


async def test_snapshot_endpoint_falls_back_to_sample(client):
    response = await client.get("/api/v1/fitness/snapshot")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "sample"
    assert len(body["stats"]) == 5
    assert len(body["heatmap"]) == 26 * 7


def _set(weight_kg=None, reps=None, set_type="normal"):
    return {
        "index": 0,
        "type": set_type,
        "weight_kg": weight_kg,
        "reps": reps,
        "distance_meters": None,
        "duration_seconds": None,
        "rpe": None,
        "custom_metric": None,
    }


def _workout(start_time, exercises):
    return {
        "id": "w1",
        "title": "Test",
        "description": None,
        "routine_id": None,
        "start_time": start_time,
        "end_time": start_time,
        "created_at": start_time,
        "updated_at": start_time,
        "exercises": exercises,
    }


def test_build_records_skips_warmups_and_keeps_higher_epley():
    workouts = [
        _workout(
            "2026-08-01T10:00:00Z",
            [
                {
                    "index": 0,
                    "title": "Bench Press",
                    "notes": None,
                    "exercise_template_id": "tpl-1",
                    "supersets_id": None,
                    "sets": [
                        _set(weight_kg=999, reps=1, set_type="warmup"),
                        _set(weight_kg=100, reps=5, set_type="normal"),
                        _set(weight_kg=90, reps=8, set_type="normal"),
                    ],
                }
            ],
        )
    ]

    records = build_records(workouts)
    assert len(records) == 1
    record = records[0]
    assert record.exercise_template_id == "tpl-1"
    # Epley(100, 5) = 100 * (1 + 5/30) ≈ 116.67; Epley(90, 8) = 90 * (1+8/30) ≈ 114
    assert record.weight_kg == 100
    assert record.estimated_one_rep_max_kg == 117


def test_build_heatmap_ends_on_sunday_and_covers_full_weeks():
    now = datetime(2026, 8, 26, 12, 0, 0, tzinfo=UTC)
    days = build_heatmap([], UTC_TZ, weeks=26, now=now)
    assert len(days) == 26 * 7
    last_day = datetime.fromisoformat(days[-1].date)
    # ISO weekday 7 = Sunday
    assert last_day.isoweekday() == 7


def test_format_tonnes_switches_precision_at_100000kg():
    assert format_tonnes(50_000) == "50.0"
    assert format_tonnes(150_000) == "150"


def test_format_count_uses_thousands_separator():
    assert format_count(12345) == "12,345"


def test_title_case_splits_on_separators():
    assert title_case("lower_back") == "Lower Back"
    assert title_case("upper-body split") == "Upper Body Split"


# --- rate limiting and failure handling ---------------------------------------------


def _unthrottled_settings(**overrides) -> Settings:
    """Real settings with the throttle wound up, so tests do not wait on it."""
    return Settings(
        hevy_api_key="test-key",
        hevy_requests_per_second=1000.0,
        hevy_request_burst=50,
        **overrides,
    )


@asynccontextmanager
async def _mock_hevy_api(handler: Callable[[httpx.Request], httpx.Response]) -> AsyncIterator[None]:
    client_module._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        yield
    finally:
        await client_module._http_client.aclose()
        client_module._http_client = None


async def test_request_retries_after_429():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(200, json={"workout_count": 7})

    async with _mock_hevy_api(handler):
        count = await HevyClient(_unthrottled_settings()).fetch_workout_count()

    assert count == 7
    assert len(calls) == 2


async def test_request_raises_once_retries_are_exhausted():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(429, headers={"retry-after": "0"})

    async with _mock_hevy_api(handler):
        with pytest.raises(HevyError) as excinfo:
            await HevyClient(_unthrottled_settings(hevy_max_retries=1)).fetch_workout_count()

    assert excinfo.value.status_code == 429
    assert len(calls) == 2


async def test_exercise_template_catalogue_is_fetched_once():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={"page": 1, "page_count": 1, "exercise_templates": [{"id": "tpl-1"}]},
        )

    async with _mock_hevy_api(handler):
        client = HevyClient(_unthrottled_settings())
        catalogue = await client.fetch_all_exercise_templates()
        by_id = await client.fetch_exercise_templates({"tpl-1"})

    assert [t["id"] for t in catalogue] == ["tpl-1"]
    assert set(by_id) == {"tpl-1"}
    assert len(calls) == 1


async def test_rate_limiter_spaces_requests_past_the_burst():
    limiter = client_module._RateLimiter(rate_per_second=50.0, burst=2)

    started = time.monotonic()
    for _ in range(4):
        await limiter.acquire()
    elapsed = time.monotonic() - started

    # Two acquires come free from the burst; the rest are spaced 20ms apart.
    assert elapsed >= 0.03


class _FakeHevyClient:
    """Serves sample payloads as if they were live, and can be flipped into failing."""

    def __init__(self, tz: ZoneInfo) -> None:
        self._tz = tz
        self.fail = False

    def _guard(self) -> None:
        if self.fail:
            raise HevyError("Hevy API 429 for /workouts", 429)

    async def fetch_workouts(self) -> list[dict]:
        self._guard()
        return sample_workouts(self._tz)

    async def fetch_routines(self) -> list[dict]:
        self._guard()
        return sample_routines()

    async def fetch_workout_count(self) -> int:
        self._guard()
        return 42

    async def fetch_exercise_templates(self, ids: set[str]) -> dict[str, dict]:
        self._guard()
        return sample_exercise_templates()


def _service(settings: Settings) -> tuple[HevySnapshotService, _FakeHevyClient]:
    fake = _FakeHevyClient(ZoneInfo(settings.hevy_timezone))
    return HevySnapshotService(settings, fake), fake  # type: ignore[arg-type]


async def test_snapshot_serves_last_live_data_when_live_fetch_fails():
    service, fake = _service(_unthrottled_settings())

    first = await service.get_training_snapshot()
    assert first.source == "live"

    fake.fail = True
    snapshot_module._cache_expires_at = 0.0
    second = await service.get_training_snapshot()

    # Stale live data beats sample data — same snapshot, original synced_at.
    assert second.source == "live"
    assert second.synced_at == first.synced_at


async def test_failed_build_is_cached_only_briefly():
    settings = _unthrottled_settings(hevy_cache_ttl_seconds=3600, hevy_fallback_cache_ttl_seconds=5)
    service, fake = _service(settings)
    fake.fail = True

    snapshot = await service.get_training_snapshot()

    assert snapshot.source == "sample"
    assert snapshot_module._cache_expires_at - time.monotonic() <= 5
