from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import HevyError, HevyNotConfiguredError

_http_client: httpx.AsyncClient | None = None


async def start_http_client() -> None:
    global _http_client
    _http_client = httpx.AsyncClient(timeout=10.0)


async def stop_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


def _client() -> httpx.AsyncClient:
    if _http_client is None:
        raise RuntimeError("Hevy HTTP client is not started")
    return _http_client


class HevyClient:
    """Thin async wrapper over the Hevy public API (https://api.hevyapp.com/docs/)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def _request(
        self, path: str, params: dict[str, str | int] | None = None
    ) -> dict[str, Any]:
        if not self._settings.hevy_configured:
            raise HevyNotConfiguredError()

        url = f"{self._settings.hevy_api_base_url}{path}"
        response = await _client().get(
            url,
            params=params,
            headers={"api-key": self._settings.hevy_api_key or "", "accept": "application/json"},
        )
        if response.is_error:
            raise HevyError(f"Hevy API {response.status_code} for {path}", response.status_code)
        return response.json()

    async def _collect(
        self,
        path: str,
        pick: Callable[[dict[str, Any]], list[Any]],
        page_size: int,
        max_pages: int,
    ) -> list[Any]:
        items: list[Any] = []
        for page in range(1, max_pages + 1):
            payload = await self._request(path, {"page": page, "pageSize": page_size})
            batch = pick(payload)
            items.extend(batch)
            if len(batch) < page_size or page >= payload.get("page_count", page):
                break
        return items

    async def fetch_workouts(self, limit_pages: int = 12) -> list[dict[str, Any]]:
        return await self._collect(
            "/workouts", lambda p: p.get("workouts", []), page_size=10, max_pages=limit_pages
        )

    async def fetch_routines(self, limit_pages: int = 2) -> list[dict[str, Any]]:
        return await self._collect(
            "/routines", lambda p: p.get("routines", []), page_size=10, max_pages=limit_pages
        )

    async def fetch_workout_count(self) -> int:
        payload = await self._request("/workouts/count")
        return payload["workout_count"]

    async def fetch_exercise_templates(self, ids: set[str]) -> dict[str, dict[str, Any]]:
        templates = await self._collect(
            "/exercise_templates",
            lambda p: p.get("exercise_templates", []),
            page_size=100,
            max_pages=20,
        )
        return {t["id"]: t for t in templates if t["id"] in ids}

    async def fetch_all_exercise_templates(self, max_pages: int = 20) -> list[dict[str, Any]]:
        return await self._collect(
            "/exercise_templates",
            lambda p: p.get("exercise_templates", []),
            page_size=100,
            max_pages=max_pages,
        )

    async def fetch_workout(self, workout_id: str) -> dict[str, Any]:
        return await self._request(f"/workouts/{workout_id}")

    async def fetch_user_info(self) -> dict[str, Any]:
        payload = await self._request("/user/info")
        return payload.get("data", payload)
