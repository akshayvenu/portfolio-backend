"""Single entry point for the Side Quest page's training snapshot.

Port of frontend/src/lib/hevy/snapshot.ts. Live Hevy data when a key is
configured, seeded sample data otherwise. A failed live fetch degrades to the
last good live snapshot, then to sample data, so an API outage shows a
complete-looking page rather than a broken one.
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

_cached_snapshot: TrainingSnapshot | None = None
_cache_expires_at: float = 0.0
_last_live_snapshot: TrainingSnapshot | None = None
_cache_lock = asyncio.Lock()


def reset_cache() -> None:
    """Drop every cached snapshot (used by tests)."""
    global _cached_snapshot, _cache_expires_at, _last_live_snapshot
    _cached_snapshot = None
    _cache_expires_at = 0.0
    _last_live_snapshot = None


class HevySnapshotService:
    def __init__(self, settings: Settings, client: HevyClient) -> None:
        self._settings = settings
        self._client = client
        self._tz = ZoneInfo(settings.hevy_timezone)

    async def get_training_snapshot(self) -> TrainingSnapshot:
        global _cached_snapshot, _cache_expires_at

        async with _cache_lock:
            if _cached_snapshot is not None and time.monotonic() < _cache_expires_at:
                return _cached_snapshot

            snapshot, ttl_seconds = await self._build_snapshot()

            _cached_snapshot = snapshot
            _cache_expires_at = time.monotonic() + ttl_seconds
            return snapshot

    async def _build_snapshot(self) -> tuple[TrainingSnapshot, int]:
        """Returns the snapshot plus how long it is worth caching."""
        global _last_live_snapshot

        if not self._settings.hevy_configured:
            return self._sample_snapshot(), self._settings.hevy_cache_ttl_seconds

        try:
            snapshot = await self._live_snapshot()
        except Exception:
            logger.exception("[hevy] live fetch failed")
            # Prefer the last good live data over sample data, and cache it only
            # briefly: a transient failure (a mid-build 429 is the usual one) should
            # not hold the page on fallback data for a full TTL.
            fallback = _last_live_snapshot or self._sample_snapshot()
            return fallback, self._settings.hevy_fallback_cache_ttl_seconds

        _last_live_snapshot = snapshot
        return snapshot, self._settings.hevy_cache_ttl_seconds

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
