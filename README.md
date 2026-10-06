# Seat Reservation at Scale

Backend take-home exercise for a high-concurrency seat reservation service.

## Stack

- FastAPI
- PostgreSQL
- SQLAlchemy
- Docker
- Prometheus-compatible metrics

## Reservation semantics

- Multi-seat requests are **all-or-nothing**.
- Seat rows are locked in deterministic seat-number order.
- Same seat under concurrency: exactly one request can confirm it.
- Business contention returns HTTP 409, not 500.
- Idempotency is scoped to `(user_id, show_id, idempotency_key)`.
- Same idempotency key + different seat set returns 409.
- Identity comes from `Authorization: Bearer <user-id>`.
- A user may hold/confirm at most `per_user_limit` seats.
- Cancellation is owner-only and returns confirmed seats to available atomically.

## Local setup

Start PostgreSQL:

```bash
docker compose up -d
```

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
```

Run API:

```bash
uvicorn app.main:app --reload
```

Open:

`http://127.0.0.1:8000/docs`

## Health

- `GET /health/live`
- `GET /health/ready`

## Metrics

`GET /metrics`

## Burst test

```bash
python scripts/burst.py http://127.0.0.1:8000
```

The burst test creates a fresh show and sends 500 concurrent requests for the same hot seat.

## Important

For the production submission, deploy PostgreSQL as a managed database and set `DATABASE_URL`. Do not use SQLite.

## AI usage

AI tools were used as an engineering assistant for scaffolding, code review, test-case generation, and documentation. The concurrency model, transaction boundaries, database constraints, and live-load behavior must be reviewed and validated by the candidate before submission.
