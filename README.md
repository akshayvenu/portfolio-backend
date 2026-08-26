# Portfolio Backend

FastAPI service for the portfolio site (health check + contact form).

## Structure

```
app/
├── main.py              # app factory + FastAPI instance
├── core/                # config, logging, exception handling
├── api/v1/               # versioned routes (/api/v1/...)
├── schemas/              # pydantic request/response models
├── services/              # business logic
└── models/                # (reserved for future ORM models)
tests/                     # pytest + httpx async tests
```

## Getting started

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs
Health check: http://localhost:8000/api/v1/health

## Testing & linting

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

## Docker

```bash
docker compose up --build
```

## Connecting the frontend

Set `CORS_ORIGINS` in `.env` to include your frontend's origin
(defaults to `http://localhost:3000` for the Next.js dev server).
In the frontend, point requests at `http://localhost:8000/api/v1`.
