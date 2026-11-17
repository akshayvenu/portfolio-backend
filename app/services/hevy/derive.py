"""Turns raw Hevy payloads into the numbers the Side Quest page renders.

Port of frontend/src/lib/hevy/derive.ts — keep function names, defaults and
arithmetic in lockstep so the numbers match the original TS implementation
exactly. Operates on raw Hevy wire dicts (as returned by `HevyClient`), not
the typed schemas, to mirror the TS module's use of the raw JSON shape.
"""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.schemas.fitness import (
    HeatmapDay,
    MuscleRadar,
    MuscleRadarAxis,
    MuscleSplitSlice,
    PeriodComparison,
    PeriodMetric,
    PersonalRecord,
    RoutineSummary,
    TrainingStat,
    WorkoutSummary,
    WorkoutSummaryExercise,
)

DAY = timedelta(days=1)

#: Hevy reports ~20 primary muscle groups; the radar reads best at six spokes, so
#: they collapse into the coarse regions a training split is actually planned
#: around. Order matters — it is the drawing order, clockwise from upper-left.
RADAR_AXES: list[tuple[str, tuple[str, ...]]] = [
    ("Back", ("lats", "upper_back", "lower_back", "traps")),
    ("Chest", ("chest",)),
    ("Core", ("abdominals",)),
    ("Shoulders", ("shoulders", "neck")),
    ("Arms", ("biceps", "triceps", "forearms")),
    ("Legs", ("quadriceps", "hamstrings", "glutes", "calves", "abductors", "adductors")),
]

_RADAR_LOOKUP: dict[str, str] = {group: axis for axis, groups in RADAR_AXES for group in groups}


def _is_working_set(s: dict) -> bool:
    return s.get("type") != "warmup"


def _set_volume(s: dict) -> float:
    if not _is_working_set(s):
        return 0
    return (s.get("weight_kg") or 0) * (s.get("reps") or 0)


def workout_volume_kg(workout: dict) -> float:
    return sum(
        _set_volume(s) for exercise in workout["exercises"] for s in exercise["sets"]
    )


def workout_set_count(workout: dict) -> int:
    return sum(
        1
        for exercise in workout["exercises"]
        for s in exercise["sets"]
        if _is_working_set(s)
    )


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def workout_minutes(workout: dict) -> int:
    try:
        delta = _parse_iso(workout["end_time"]) - _parse_iso(workout["start_time"])
        return max(0, round(delta.total_seconds() / 60))
    except (ValueError, KeyError):
        return 0


def _day_key(iso: str, tz: ZoneInfo) -> str:
    return _parse_iso(iso).astimezone(tz).date().isoformat()


def _estimate_one_rep_max(weight_kg: float, reps: float) -> float:
    if reps <= 1:
        return weight_kg
    return weight_kg * (1 + reps / 30)


def _week_key(d: date) -> str:
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


def weekly_streak(workouts: list[dict], tz: ZoneInfo, now: datetime | None = None) -> int:
    now = now or datetime.now(tz)
    weeks = {_week_key(_parse_iso(w["start_time"]).astimezone(tz).date()) for w in workouts}

    streak = 0
    cursor = now.astimezone(tz).date()
    while _week_key(cursor) in weeks:
        streak += 1
        cursor -= timedelta(days=7)
    return streak


def build_heatmap(
    workouts: list[dict], tz: ZoneInfo, weeks: int = 26, now: datetime | None = None
) -> list[HeatmapDay]:
    now = now or datetime.now(tz)
    by_day: dict[str, dict[str, float]] = {}

    for workout in workouts:
        key = _day_key(workout["start_time"], tz)
        entry = by_day.setdefault(key, {"workouts": 0, "volumeKg": 0.0})
        entry["workouts"] += 1
        entry["volumeKg"] += workout_volume_kg(workout)

    # Finish on the Sunday of the current week so every column is a full week.
    today = now.astimezone(tz).date()
    end = today + timedelta(days=(6 - today.weekday()))

    volumes = sorted(entry["volumeKg"] for entry in by_day.values())

    days: list[HeatmapDay] = []
    for index in range(weeks * 7 - 1, -1, -1):
        d = end - timedelta(days=index)
        key = d.isoformat()
        entry = by_day.get(key)
        days.append(
            HeatmapDay(
                date=key,
                workouts=int(entry["workouts"]) if entry else 0,
                volume_kg=round(entry["volumeKg"]) if entry else 0,
                level=_intensity_level(entry["volumeKg"], volumes) if entry else 0,
            )
        )

    return days


def _intensity_level(volume: float, sorted_volumes: list[float]) -> int:
    if not sorted_volumes:
        return 1

    def quartile(fraction: float) -> float:
        idx = int((len(sorted_volumes) - 1) * fraction)
        return sorted_volumes[idx]

    if volume >= quartile(0.75):
        return 4
    if volume >= quartile(0.5):
        return 3
    if volume >= quartile(0.25):
        return 2
    return 1


def build_muscle_split(
    workouts: list[dict], templates: dict[str, dict], limit: int = 6
) -> list[MuscleSplitSlice]:
    by_sets: dict[str, int] = {}

    for workout in workouts:
        for exercise in workout["exercises"]:
            template = templates.get(exercise["exercise_template_id"])
            if not template:
                continue
            muscle = template["primary_muscle_group"]
            sets = sum(1 for s in exercise["sets"] if _is_working_set(s))
            by_sets[muscle] = by_sets.get(muscle, 0) + sets

    total = sum(by_sets.values())
    if total == 0:
        return []

    slices = [
        MuscleSplitSlice(muscle=title_case(muscle), sets=sets, share=sets / total)
        for muscle, sets in by_sets.items()
    ]
    slices.sort(key=lambda s: s.sets, reverse=True)
    return slices[:limit]


def _split_windows(
    workouts: list[dict], window_days: int, now: datetime
) -> tuple[list[dict], list[dict]]:
    """Workouts in the last `window_days`, and in the equal-length window before it."""
    current_start = now - window_days * DAY
    previous_start = current_start - window_days * DAY

    current, previous = [], []
    for workout in workouts:
        started = _parse_iso(workout["start_time"])
        if started >= current_start:
            current.append(workout)
        elif started >= previous_start:
            previous.append(workout)
    return current, previous


def _radar_sets(workouts: list[dict], templates: dict[str, dict]) -> dict[str, int]:
    by_axis: dict[str, int] = {}
    for workout in workouts:
        for exercise in workout["exercises"]:
            template = templates.get(exercise["exercise_template_id"])
            if not template:
                continue
            # Cardio / full-body templates have no honest home on a six-spoke
            # split, so they sit the chart out rather than distorting a region.
            axis = _RADAR_LOOKUP.get(template["primary_muscle_group"])
            if not axis:
                continue
            by_axis[axis] = by_axis.get(axis, 0) + sum(
                1 for s in exercise["sets"] if _is_working_set(s)
            )
    return by_axis


def build_muscle_radar(
    workouts: list[dict],
    templates: dict[str, dict],
    tz: ZoneInfo,
    window_days: int = 30,
    now: datetime | None = None,
) -> MuscleRadar:
    """Set distribution across six muscle regions, this window against the last.

    Shares rather than raw counts: the point of the overlay is whether the shape
    of the split moved, which a heavier month would otherwise swamp.
    """
    now = now or datetime.now(tz)
    current_workouts, previous_workouts = _split_windows(workouts, window_days, now)

    current = _radar_sets(current_workouts, templates)
    previous = _radar_sets(previous_workouts, templates)
    current_total = sum(current.values())
    previous_total = sum(previous.values())

    axes = [
        MuscleRadarAxis(
            muscle=axis,
            current_sets=current.get(axis, 0),
            previous_sets=previous.get(axis, 0),
            current_share=current.get(axis, 0) / current_total if current_total else 0.0,
            previous_share=previous.get(axis, 0) / previous_total if previous_total else 0.0,
        )
        for axis, _ in RADAR_AXES
    ]

    return MuscleRadar(window_days=window_days, axes=axes)


def _format_minutes(minutes: int) -> tuple[str, str | None]:
    if minutes < 60:
        return str(minutes), "min"
    hours, rest = divmod(minutes, 60)
    return (f"{hours}h {rest}min" if rest else f"{hours}h"), None


def build_period_comparison(
    workouts: list[dict],
    tz: ZoneInfo,
    window_days: int = 30,
    now: datetime | None = None,
) -> PeriodComparison:
    """The four headline numbers for the window, each with its period-on-period move."""
    now = now or datetime.now(tz)
    current, previous = _split_windows(workouts, window_days, now)

    def totals(bucket: list[dict]) -> dict[str, int]:
        return {
            "workouts": len(bucket),
            "duration": sum(workout_minutes(w) for w in bucket),
            "volume": round(sum(workout_volume_kg(w) for w in bucket)),
            "sets": sum(workout_set_count(w) for w in bucket),
        }

    now_totals, then_totals = totals(current), totals(previous)

    def metric(
        metric_id: str, label: str, value: str, unit: str | None, delta_text: str | None
    ) -> PeriodMetric:
        change = now_totals[metric_id] - then_totals[metric_id]
        direction = "up" if change > 0 else "down" if change < 0 else "flat"
        return PeriodMetric(
            id=metric_id,
            label=label,
            value=value,
            unit=unit,
            delta=delta_text if change else None,
            direction=direction,
        )

    duration_value, duration_unit = _format_minutes(now_totals["duration"])
    duration_change = abs(now_totals["duration"] - then_totals["duration"])
    duration_delta, duration_delta_unit = _format_minutes(duration_change)
    volume_change = now_totals["volume"] - then_totals["volume"]

    return PeriodComparison(
        window_days=window_days,
        metrics=[
            metric(
                "workouts",
                "Workouts",
                format_count(now_totals["workouts"]),
                None,
                format_count(abs(now_totals["workouts"] - then_totals["workouts"])),
            ),
            metric(
                "duration",
                "Duration",
                duration_value,
                duration_unit,
                f"{duration_delta}{duration_delta_unit or ''}",
            ),
            metric(
                "volume",
                "Volume",
                format_count(now_totals["volume"]),
                "kg",
                f"{format_count(abs(volume_change))} kg",
            ),
            metric(
                "sets",
                "Sets",
                format_count(now_totals["sets"]),
                None,
                format_count(abs(now_totals["sets"] - then_totals["sets"])),
            ),
        ],
    )


def build_records(workouts: list[dict], limit: int | None = 5) -> list[PersonalRecord]:
    best: dict[str, PersonalRecord] = {}

    for workout in workouts:
        for exercise in workout["exercises"]:
            for s in exercise["sets"]:
                weight_kg = s.get("weight_kg")
                reps = s.get("reps")
                if not _is_working_set(s) or not weight_kg or not reps:
                    continue

                estimate = _estimate_one_rep_max(weight_kg, reps)
                template_id = exercise["exercise_template_id"]
                current = best.get(template_id)
                if current and current.estimated_one_rep_max_kg >= estimate:
                    continue

                best[template_id] = PersonalRecord(
                    exercise=exercise["title"],
                    exercise_template_id=template_id,
                    weight_kg=weight_kg,
                    reps=reps,
                    estimated_one_rep_max_kg=round(estimate),
                    date=workout["start_time"],
                )

    records = sorted(best.values(), key=lambda r: r.estimated_one_rep_max_kg, reverse=True)
    return records[:limit] if limit is not None else records


def summarise_workouts(
    workouts: list[dict], templates: dict[str, dict], limit: int = 6
) -> list[WorkoutSummary]:
    # Records are computed over the whole history so a "PR" badge on a recent
    # session means an all-time best, not merely the best of that session.
    all_time = {record.exercise_template_id: record for record in build_records(workouts, None)}

    sorted_workouts = sorted(workouts, key=lambda w: w["start_time"], reverse=True)[:limit]

    summaries = []
    for workout in sorted_workouts:
        pr_count = sum(
            1
            for exercise in workout["exercises"]
            if all_time.get(exercise["exercise_template_id"])
            and all_time[exercise["exercise_template_id"]].date == workout["start_time"]
        )
        exercises = []
        for exercise in workout["exercises"]:
            template = templates.get(exercise["exercise_template_id"])
            exercises.append(
                WorkoutSummaryExercise(
                    title=exercise["title"],
                    sets=sum(1 for s in exercise["sets"] if _is_working_set(s)),
                    top_set=_describe_top_set(exercise["sets"]),
                    muscle=title_case(template["primary_muscle_group"]) if template else None,
                )
            )

        summaries.append(
            WorkoutSummary(
                id=workout["id"],
                title=workout["title"],
                start_time=workout["start_time"],
                duration_minutes=workout_minutes(workout),
                volume_kg=round(workout_volume_kg(workout)),
                sets=workout_set_count(workout),
                pr_count=pr_count,
                exercises=exercises,
            )
        )

    return summaries


def _describe_top_set(sets: list[dict]) -> str:
    working = [s for s in sets if _is_working_set(s)]
    if not working:
        return "—"

    heaviest = max(working, key=_set_volume)
    weight_kg = heaviest.get("weight_kg")
    reps = heaviest.get("reps")
    if weight_kg and reps:
        return f"{format_kg(weight_kg)} × {int(reps)}"
    if heaviest.get("duration_seconds"):
        return f"{round(heaviest['duration_seconds'] / 60)} min"
    if heaviest.get("distance_meters"):
        return f"{heaviest['distance_meters'] / 1000:.2f} km"
    if reps:
        return f"{int(reps)} reps"
    return "—"


def summarise_routines(
    routines: list[dict], templates: dict[str, dict], limit: int = 4
) -> list[RoutineSummary]:
    summaries = []
    for routine in routines[:limit]:
        muscles: list[str] = []
        for exercise in routine["exercises"]:
            template = templates.get(exercise["exercise_template_id"])
            if template:
                muscle = title_case(template["primary_muscle_group"])
                if muscle not in muscles:
                    muscles.append(muscle)

        summaries.append(
            RoutineSummary(
                id=routine["id"],
                title=routine["title"],
                exercise_count=len(routine["exercises"]),
                set_count=sum(len(exercise["sets"]) for exercise in routine["exercises"]),
                focus=muscles[:4],
            )
        )
    return summaries


def build_stats(workouts: list[dict], total_workouts: int, tz: ZoneInfo) -> list[TrainingStat]:
    now = datetime.now(tz)
    since_cutoff = now - 30 * DAY
    last_thirty = [w for w in workouts if _parse_iso(w["start_time"]) >= since_cutoff]

    volume = sum(workout_volume_kg(w) for w in workouts)
    minutes = sum(workout_minutes(w) for w in workouts)
    average_minutes = round(minutes / len(workouts)) if workouts else 0

    return [
        TrainingStat(
            id="workouts",
            label="Sessions logged",
            value=format_count(total_workouts),
            hint="All time, via Hevy",
        ),
        TrainingStat(
            id="volume",
            label="Volume moved",
            value=format_tonnes(volume),
            unit="t",
            hint=f"Across the last {len(workouts)} sessions",
        ),
        TrainingStat(
            id="streak",
            label="Weekly streak",
            value=str(weekly_streak(workouts, tz, now)),
            unit="wks",
            hint="Consecutive weeks trained",
        ),
        TrainingStat(
            id="cadence",
            label="Cadence",
            value=f"{len(last_thirty) / 4.3:.1f}",
            unit="/wk",
            hint="Rolling 30 days",
        ),
        TrainingStat(
            id="duration",
            label="Average session",
            value=str(average_minutes),
            unit="min",
            hint="Door to door",
        ),
    ]


def format_kg(value: float) -> str:
    formatted = str(int(value)) if value == int(value) else f"{value:.1f}"
    return f"{formatted} kg"


def format_tonnes(kg: float) -> str:
    tonnes = kg / 1000
    return f"{tonnes:.0f}" if kg >= 100_000 else f"{tonnes:.1f}"


def format_count(value: int) -> str:
    return f"{value:,}"


def title_case(value: str) -> str:
    words = re.split(r"[\s_-]+", value)
    return " ".join(w[:1].upper() + w[1:] for w in words if w)
