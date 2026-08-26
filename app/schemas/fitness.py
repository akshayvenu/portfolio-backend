from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# --------------------------------------------------------------------------- #
# Wire models — transcribed from https://api.hevyapp.com/docs/ (snake_case,   #
# nullable metric fields). Mirrors frontend/src/types/hevy.ts.                #
# --------------------------------------------------------------------------- #


class HevySet(BaseModel):
    index: int
    type: str
    weight_kg: float | None = None
    reps: float | None = None
    distance_meters: float | None = None
    duration_seconds: float | None = None
    rpe: float | None = None
    custom_metric: float | None = None


class HevyWorkoutExercise(BaseModel):
    index: int
    title: str
    notes: str | None = None
    exercise_template_id: str
    supersets_id: int | None = None
    sets: list[HevySet] = []


class HevyWorkout(BaseModel):
    id: str
    title: str
    description: str | None = None
    routine_id: str | None = None
    start_time: str
    end_time: str
    created_at: str
    updated_at: str
    exercises: list[HevyWorkoutExercise] = []


class HevyExerciseTemplate(BaseModel):
    id: str
    title: str
    type: str
    primary_muscle_group: str
    secondary_muscle_groups: list[str] = []
    equipment_category: str | None = None
    is_custom: bool = False


class HevyRoutineExercise(BaseModel):
    index: int
    title: str
    rest_seconds: int | str | None = None
    notes: str | None = None
    exercise_template_id: str
    supersets_id: int | None = None
    sets: list[HevySet] = []


class HevyRoutine(BaseModel):
    id: str
    title: str
    folder_id: int | None = None
    created_at: str
    updated_at: str
    exercises: list[HevyRoutineExercise] = []


class HevyUserInfo(BaseModel):
    id: str
    name: str
    url: str


# --------------------------------------------------------------------------- #
# Derived view models — what the Side Quest page renders. Serialised          #
# camelCase so `TrainingSnapshot` matches frontend/src/types/hevy.ts exactly. #
# --------------------------------------------------------------------------- #


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TrainingStat(CamelModel):
    id: str
    label: str
    value: str
    unit: str | None = None
    hint: str | None = None


class HeatmapDay(CamelModel):
    date: str
    level: int
    workouts: int
    volume_kg: float


class MuscleSplitSlice(CamelModel):
    muscle: str
    sets: int
    share: float


class PersonalRecord(CamelModel):
    exercise: str
    exercise_template_id: str
    weight_kg: float
    reps: float
    estimated_one_rep_max_kg: float
    date: str


class WorkoutSummaryExercise(CamelModel):
    title: str
    sets: int
    top_set: str
    muscle: str | None = None


class WorkoutSummary(CamelModel):
    id: str
    title: str
    start_time: str
    duration_minutes: int
    volume_kg: float
    sets: int
    pr_count: int
    exercises: list[WorkoutSummaryExercise] = []


class RoutineSummary(CamelModel):
    id: str
    title: str
    exercise_count: int
    set_count: int
    focus: list[str] = []


class TrainingSnapshot(CamelModel):
    source: str
    synced_at: str
    stats: list[TrainingStat]
    heatmap: list[HeatmapDay]
    muscle_split: list[MuscleSplitSlice]
    records: list[PersonalRecord]
    workouts: list[WorkoutSummary]
    routines: list[RoutineSummary]
