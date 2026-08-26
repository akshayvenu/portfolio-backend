from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.hevy import snapshot as snapshot_module
from app.services.hevy.derive import (
    build_heatmap,
    build_records,
    format_count,
    format_tonnes,
    title_case,
)

UTC_TZ = ZoneInfo("UTC")


@pytest.fixture(autouse=True)
def _reset_hevy_cache() -> None:
    snapshot_module._cache["value"] = None
    snapshot_module._cache["expires_at"] = 0.0


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
