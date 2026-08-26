"""Single entry point for the Side Quest page's training snapshot.

Port of frontend/src/lib/hevy/snapshot.ts. Live Hevy data when a key is
configured, seeded sample data otherwise — and the sample path is also the
failure path, so an API outage degrades to a complete-looking page rather
than a broken one.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.schemas.fitness import TrainingSnapshot
from app.services.hevy.client import HevyClient
from app.services.hevy.derive import (
    build_heatmap,
    build_muscle_split,
    build_records,
    build_stats,
    summarise_routines,
    summarise_workouts,
)
from app.services.hevy.sample import sample_exercise_templates, sample_routines, sample_workouts

logger = logging.getLogger(__name__)

_cache: dict[str, object] = {"value": None, "expires_at": 0.0}
_cache_lock = asyncio.Lock()


class HevySnapshotService:
    def __init__(self, settings: Settings, client: HevyClient) -> None:
        self._settings = settings
        self._client = client
        self._tz = ZoneInfo(settings.hevy_timezone)

    async def get_training_snapshot(self) -> TrainingSnapshot:
        async with _cache_lock:
            cached = _cache["value"]
            if cached is not None and time.monotonic() < _cache["expires_at"]:
                return cached  # type: ignore[return-value]

            snapshot = await self._build_snapshot()

            _cache["value"] = snapshot
            _cache["expires_at"] = time.monotonic() + self._settings.hevy_cache_ttl_seconds
            return snapshot

    async def _build_snapshot(self) -> TrainingSnapshot:
        if self._settings.hevy_configured:
            try:
                return await self._live_snapshot()
            except Exception:
                logger.exception("[hevy] falling back to sample data")

        return self._sample_snapshot()

    async def _live_snapshot(self) -> TrainingSnapshot:
        workouts, routines, total_workouts = await asyncio.gather(
            self._client.fetch_workouts(),
            self._client.fetch_routines(),
            self._client.fetch_workout_count(),
        )

        referenced = {
            exercise["exercise_template_id"]
            for workout in workouts
            for exercise in workout["exercises"]
        } | {
            exercise["exercise_template_id"]
            for routine in routines
            for exercise in routine["exercises"]
        }
        templates = await self._client.fetch_exercise_templates(referenced)

        return self._assemble("live", workouts, routines, templates, total_workouts)

    def _sample_snapshot(self) -> TrainingSnapshot:
        workouts = sample_workouts(self._tz)
        return self._assemble(
            "sample", workouts, sample_routines(), sample_exercise_templates(), len(workouts)
        )

    def _assemble(
        self,
        source: str,
        workouts: list[dict],
        routines: list[dict],
        templates: dict[str, dict],
        total_workouts: int,
    ) -> TrainingSnapshot:
        return TrainingSnapshot(
            source=source,
            synced_at=datetime.now(UTC).isoformat(),
            stats=build_stats(workouts, total_workouts, self._tz),
            heatmap=build_heatmap(workouts, self._tz),
            muscle_split=build_muscle_split(workouts, templates),
            records=build_records(workouts),
            workouts=summarise_workouts(workouts, templates),
            routines=summarise_routines(routines, templates),
        )
