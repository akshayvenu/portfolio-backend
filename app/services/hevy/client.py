import asyncio
import logging
import random
import time
from collections.abc import Callable
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import HevyError, HevyNotConfiguredError

logger = logging.getLogger(__name__)

# Hevy does not document a rate limit, but a snapshot build is ~25 paged requests and
# the API starts answering 429 somewhere around 5 requests/second. Everything below
# keeps a build inside that budget instead of racing into a 429.
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_DELAY_SECONDS = 30.0
_TEMPLATE_MAX_PAGES = 20

_http_client: httpx.AsyncClient | None = None
_limiter: "_RateLimiter | None" = None

# The exercise template catalogue is static reference data shared by every caller.
_templates: list[dict[str, Any]] | None = None
_templates_expires_at: float = 0.0
_templates_lock = asyncio.Lock()


class _RateLimiter:
    """Token bucket shared by every Hevy request in the process.

    A burst covers the concurrent first page of each resource; after that requests
    are spaced out. `pause` lets a 429 slow down the sibling requests too, so one
    rate-limited page does not take the rest of the build down with it.
    """

    def __init__(self, rate_per_second: float, burst: int) -> None:
        self._rate = max(rate_per_second, 0.1)
        self._burst = max(burst, 1)
        self._tokens = float(self._burst)
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                elapsed = time.monotonic() - self._updated_at
                if elapsed < 0:  # paused by a 429
                    await asyncio.sleep(-elapsed)
                    continue

                self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
                self._updated_at += elapsed
                if self._tokens >= 1:
                    self._tokens -= 1
                    return

                await asyncio.sleep((1 - self._tokens) / self._rate)

    async def pause(self, seconds: float) -> None:
        async with self._lock:
            self._tokens = 0.0
            self._updated_at = max(self._updated_at, time.monotonic() + seconds)


async def start_http_client() -> None:
    global _http_client
    _http_client = httpx.AsyncClient(timeout=10.0)


async def stop_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


def reset_caches() -> None:
    """Drop the shared limiter and template catalogue (used by tests)."""
    global _limiter, _templates, _templates_expires_at
    _limiter = None
    _templates = None
    _templates_expires_at = 0.0


def _client() -> httpx.AsyncClient:
    if _http_client is None:
        raise RuntimeError("Hevy HTTP client is not started")
    return _http_client


def _rate_limiter(settings: Settings) -> _RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = _RateLimiter(settings.hevy_requests_per_second, settings.hevy_request_burst)
    return _limiter


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """Retry-After when Hevy sends one, exponential backoff with jitter otherwise."""
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return min(float(retry_after), _MAX_RETRY_DELAY_SECONDS)
        except ValueError:
            pass
        try:
            retry_at = parsedate_to_datetime(retry_after)
        except (TypeError, ValueError):
            retry_at = None
        if retry_at is not None:
            seconds = (retry_at - datetime.now(retry_at.tzinfo)).total_seconds()
            return min(max(seconds, 0.0), _MAX_RETRY_DELAY_SECONDS)

    backoff = min(2.0 ** (attempt - 1), _MAX_RETRY_DELAY_SECONDS)
    return backoff + random.uniform(0.0, 0.25)


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
        headers = {
            "api-key": self._settings.hevy_api_key or "",
            "accept": "application/json",
        }
        limiter = _rate_limiter(self._settings)
        attempts = max(self._settings.hevy_max_retries, 0) + 1

        for attempt in range(1, attempts + 1):
            await limiter.acquire()
            response = await _client().get(url, params=params, headers=headers)
            if not response.is_error:
                return response.json()

            if response.status_code not in _RETRY_STATUS or attempt == attempts:
                raise HevyError(
                    f"Hevy API {response.status_code} for {path}", response.status_code
                )

            delay = _retry_delay(response, attempt)
            logger.warning(
                "[hevy] %s for %s, retrying in %.1fs (attempt %d/%d)",
                response.status_code,
                path,
                delay,
                attempt,
                attempts,
            )
            await limiter.pause(delay)

        raise HevyError(f"Hevy API request to {path} exhausted retries")

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
        templates = await self.fetch_all_exercise_templates()
        return {t["id"]: t for t in templates if t["id"] in ids}

    async def fetch_all_exercise_templates(self) -> list[dict[str, Any]]:
        """The catalogue is ~11 paged requests — the bulk of a snapshot build.

        It is also global, static data, so it is cached far longer than a snapshot:
        refetching it every rebuild is what pushes a build into the rate limit.
        """
        global _templates, _templates_expires_at

        async with _templates_lock:
            if _templates is not None and time.monotonic() < _templates_expires_at:
                return _templates

            templates = await self._collect(
                "/exercise_templates",
                lambda p: p.get("exercise_templates", []),
                page_size=100,
                max_pages=_TEMPLATE_MAX_PAGES,
            )
            _templates = templates
            _templates_expires_at = (
                time.monotonic() + self._settings.hevy_template_cache_ttl_seconds
            )
            return templates

    async def fetch_workout(self, workout_id: str) -> dict[str, Any]:
        return await self._request(f"/workouts/{workout_id}")

    async def fetch_user_info(self) -> dict[str, Any]:
        payload = await self._request("/user/info")
        return payload.get("data", payload)
