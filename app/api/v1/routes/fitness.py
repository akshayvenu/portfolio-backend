from fastapi import APIRouter

from app.api.deps import HevyClientDep, HevySnapshotServiceDep
from app.schemas.fitness import (
    HevyExerciseTemplate,
    HevyRoutine,
    HevyUserInfo,
    HevyWorkout,
    TrainingSnapshot,
)

router = APIRouter(prefix="/fitness", tags=["fitness"])


@router.get("/snapshot", response_model=TrainingSnapshot)
async def get_snapshot(snapshot_service: HevySnapshotServiceDep) -> TrainingSnapshot:
    return await snapshot_service.get_training_snapshot()


@router.get("/workouts", response_model=list[HevyWorkout])
async def list_workouts(client: HevyClientDep) -> list[dict]:
    return await client.fetch_workouts()


@router.get("/workouts/count")
async def get_workout_count(client: HevyClientDep) -> dict[str, int]:
    return {"count": await client.fetch_workout_count()}


@router.get("/workouts/{workout_id}", response_model=HevyWorkout)
async def get_workout(workout_id: str, client: HevyClientDep) -> dict:
    return await client.fetch_workout(workout_id)


@router.get("/routines", response_model=list[HevyRoutine])
async def list_routines(client: HevyClientDep) -> list[dict]:
    return await client.fetch_routines()


@router.get("/exercise-templates", response_model=list[HevyExerciseTemplate])
async def list_exercise_templates(client: HevyClientDep) -> list[dict]:
    return await client.fetch_all_exercise_templates()


@router.get("/user", response_model=HevyUserInfo)
async def get_user_info(client: HevyClientDep) -> dict:
    return await client.fetch_user_info()
