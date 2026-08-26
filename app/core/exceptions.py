from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application error mapped to a JSON response."""

    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class RateLimitedError(AppError):
    def __init__(self, detail: str = "Too many requests, please try again later.") -> None:
        super().__init__(detail, status_code=status.HTTP_429_TOO_MANY_REQUESTS)


class HevyError(AppError):
    def __init__(self, detail: str, status_code: int = status.HTTP_502_BAD_GATEWAY) -> None:
        super().__init__(detail, status_code=status_code)


class HevyNotConfiguredError(AppError):
    def __init__(self, detail: str = "HEVY_API_KEY is not configured.") -> None:
        super().__init__(detail, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": jsonable_encoder(exc.errors())},
    )


def register_exception_handlers(app) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
