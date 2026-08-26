import logging
import time
from collections import defaultdict

from app.core.config import Settings
from app.core.exceptions import RateLimitedError
from app.schemas.contact import ContactRequest, ContactResponse

logger = logging.getLogger(__name__)

_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_REQUESTS = 3

# NOTE: in-memory, per-process. Fine for a single-instance deployment; move to
# Redis (or similar) if the API ever runs behind multiple replicas.
_submission_log: dict[str, list[float]] = defaultdict(list)


class ContactService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def submit(self, payload: ContactRequest, client_ip: str) -> ContactResponse:
        self._enforce_rate_limit(client_ip)

        logger.info(
            "Contact form submission from %s <%s>: %s",
            payload.name,
            payload.email,
            payload.message,
        )

        return ContactResponse(success=True, message="Thanks! Your message has been received.")

    def _enforce_rate_limit(self, client_ip: str) -> None:
        now = time.monotonic()
        recent = [
            ts
            for ts in _submission_log[client_ip]
            if now - ts < _RATE_LIMIT_WINDOW_SECONDS
        ]
        if len(recent) >= _RATE_LIMIT_MAX_REQUESTS:
            raise RateLimitedError()

        recent.append(now)
        _submission_log[client_ip] = recent
