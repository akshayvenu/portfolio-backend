"""Seeded stand-in data, in the exact wire shape of the Hevy API.

Port of frontend/src/lib/hevy/sample.ts. The page renders identically with or
without HEVY_API_KEY: no key means these payloads flow through the same
derivation code. The generator is deterministic (fixed LCG seed) so builds
don't churn.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_TEMPLATES: list[dict] = [
    {
        "id": "D04AC939",
        "title": "Bench Press (Barbell)",
        "primary": "chest",
        "secondary": ["triceps", "shoulders"],
        "equipment": "barbell",
    },
    {
        "id": "C6272009",
        "title": "Squat (Barbell)",
        "primary": "quadriceps",
        "secondary": ["glutes", "hamstrings"],
        "equipment": "barbell",
    },
    {
        "id": "6A6C31A5",
        "title": "Deadlift (Barbell)",
        "primary": "lower_back",
        "secondary": ["hamstrings", "glutes"],
        "equipment": "barbell",
    },
    {
        "id": "7B8D84E8",
        "title": "Pull Up",
        "primary": "lats",
        "secondary": ["biceps"],
        "equipment": "none",
    },
    {
        "id": "878CD1D0",
        "title": "Overhead Press (Barbell)",
        "primary": "shoulders",
        "secondary": ["triceps"],
        "equipment": "barbell",
    },
    {
        "id": "50DFDFAB",
        "title": "Barbell Row",
        "primary": "upper_back",
        "secondary": ["lats", "biceps"],
        "equipment": "barbell",
    },
    {
        "id": "2B4B7310",
        "title": "Incline Dumbbell Press",
        "primary": "chest",
        "secondary": ["shoulders"],
        "equipment": "dumbbell",
    },
    {
        "id": "A5FDC0F4",
        "title": "Romanian Deadlift",
        "primary": "hamstrings",
        "secondary": ["glutes"],
        "equipment": "barbell",
    },
    {
        "id": "F1E5C4A2",
        "title": "Lat Pulldown (Cable)",
        "primary": "lats",
        "secondary": ["biceps"],
        "equipment": "machine",
    },
    {
        "id": "9D0F1B77",
        "title": "Bicep Curl (Dumbbell)",
        "primary": "biceps",
        "secondary": [],
        "equipment": "dumbbell",
    },
    {
        "id": "3C2A6E10",
        "title": "Triceps Rope Pushdown",
        "primary": "triceps",
        "secondary": [],
        "equipment": "machine",
    },
    {
        "id": "5E9A2D41",
        "title": "Leg Press",
        "primary": "quadriceps",
        "secondary": ["glutes"],
        "equipment": "machine",
    },
]

_DAYS: list[dict] = [
    {
        "title": "Push — Chest & Shoulders",
        "exercises": ["D04AC939", "878CD1D0", "2B4B7310", "3C2A6E10"],
    },
    {
        "title": "Pull — Back & Biceps",
        "exercises": ["7B8D84E8", "50DFDFAB", "F1E5C4A2", "9D0F1B77"],
    },
    {"title": "Legs — Squat Focus", "exercises": ["C6272009", "A5FDC0F4", "5E9A2D41"]},
    {"title": "Pull — Deadlift Focus", "exercises": ["6A6C31A5", "50DFDFAB", "9D0F1B77"]},
]

_BASE_WEIGHT: dict[str, float] = {
    "D04AC939": 70,
    "C6272009": 95,
    "6A6C31A5": 120,
    "7B8D84E8": 0,
    "878CD1D0": 45,
    "50DFDFAB": 60,
    "2B4B7310": 26,
    "A5FDC0F4": 80,
    "F1E5C4A2": 55,
    "9D0F1B77": 14,
    "3C2A6E10": 30,
    "5E9A2D41": 160,
}

_WEEKDAYS = [1, 2, 4, 5]  # Mon/Tue/Thu/Fri (Monday = 1, matching JS getDay())


def _seeded_random(seed: int):
    state = {"v": seed}

    def next_value() -> float:
        state["v"] = (state["v"] * 1664525 + 1013904223) % 4294967296
        return state["v"] / 4294967296

    return next_value


def _round_to_plate(value: float) -> float:
    return round(value / 2.5) * 2.5


def sample_exercise_templates() -> dict[str, dict]:
    return {
        t["id"]: {
            "id": t["id"],
            "title": t["title"],
            "type": "weight_reps",
            "primary_muscle_group": t["primary"],
            "secondary_muscle_groups": t["secondary"],
            "equipment_category": t["equipment"],
            "is_custom": False,
        }
        for t in _TEMPLATES
    }


def sample_workouts(tz: ZoneInfo, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(tz)
    random = _seeded_random(20240817)
    templates = sample_exercise_templates()
    workouts: list[dict] = []

    for week in range(25, -1, -1):
        sessions_this_week = 2 if random() < 0.12 else len(_WEEKDAYS)

        for slot in range(sessions_this_week):
            day = _DAYS[(week * len(_WEEKDAYS) + slot) % len(_DAYS)]

            start = now.replace(hour=7, minute=15, second=0, microsecond=0)
            # JS getDay(): Sun=0..Sat=6; Python weekday(): Mon=0..Sun=6.
            js_day = (start.weekday() + 1) % 7
            offset_to_monday = (js_day + 6) % 7
            start = start - timedelta(
                days=offset_to_monday + week * 7 - (_WEEKDAYS[slot] - 1)
            )

            if start > now:
                continue

            end = start + timedelta(minutes=52 + round(random() * 26))
            progress = 1 + (25 - week) * 0.006

            exercises = []
            for index, template_id in enumerate(day["exercises"]):
                base = _BASE_WEIGHT.get(template_id, 40)
                weight = 0 if base == 0 else _round_to_plate(base * progress + random() * 4)

                set_count = 4 if index == 0 else 3
                sets = []
                for set_index in range(set_count):
                    sets.append(
                        {
                            "index": set_index,
                            "type": "warmup" if set_index == 0 and index == 0 else "normal",
                            "weight_kg": weight or None,
                            "reps": 6 + int(random() * 5),
                            "distance_meters": None,
                            "duration_seconds": None,
                            "rpe": 7 + round(random()),
                            "custom_metric": None,
                        }
                    )

                exercises.append(
                    {
                        "index": index,
                        "title": templates[template_id]["title"],
                        "notes": None,
                        "exercise_template_id": template_id,
                        "supersets_id": None,
                        "sets": sets,
                    }
                )

            workouts.append(
                {
                    "id": f"sample-{week}-{slot}",
                    "title": day["title"],
                    "description": None,
                    "routine_id": f"routine-{day['title']}",
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                    "created_at": start.isoformat(),
                    "updated_at": end.isoformat(),
                    "exercises": exercises,
                }
            )

    return workouts


def sample_routines() -> list[dict]:
    templates = sample_exercise_templates()
    routines = []
    for index, day in enumerate(_DAYS):
        exercises = []
        for exercise_index, template_id in enumerate(day["exercises"]):
            set_count = 4 if exercise_index == 0 else 3
            sets = [
                {
                    "index": set_index,
                    "type": "normal",
                    "weight_kg": _BASE_WEIGHT.get(template_id),
                    "reps": 8,
                    "rep_range": {"start": 6, "end": 10},
                    "distance_meters": None,
                    "duration_seconds": None,
                    "rpe": None,
                    "custom_metric": None,
                }
                for set_index in range(set_count)
            ]
            exercises.append(
                {
                    "index": exercise_index,
                    "title": templates[template_id]["title"],
                    "rest_seconds": "150",
                    "notes": None,
                    "exercise_template_id": template_id,
                    "supersets_id": None,
                    "sets": sets,
                }
            )

        routines.append(
            {
                "id": f"routine-{index}",
                "title": day["title"],
                "folder_id": None,
                "created_at": "2025-01-06T06:00:00Z",
                "updated_at": "2025-08-04T06:00:00Z",
                "exercises": exercises,
            }
        )

    return routines
