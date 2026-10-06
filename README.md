# Seat Reservation at Scale

A production-oriented backend service for **high-concurrency seat reservations**, built as a backend engineering take-home assignment.

The system focuses on concurrency control, idempotency, per-user limits, transactional consistency, observability, health checks, and deployment readiness.

## 🔗 Live Links

| Resource | Link |
|---|---|
| **Live API** | https://seat-reservation-service-81no.onrender.com |
| **Swagger / OpenAPI** | https://seat-reservation-service-81no.onrender.com/docs |
| **ReDoc** | https://seat-reservation-service-81no.onrender.com/redoc |
| **Health / Readiness** | https://seat-reservation-service-81no.onrender.com/health/ready |
| **Prometheus Metrics** | https://seat-reservation-service-81no.onrender.com/metrics |
| **GitHub Repository** | https://github.com/PiyushTiwari01/seat-reservation-service |

## 🎯 Problem Statement

Build a seat reservation API that remains correct under heavy concurrent traffic.

Key requirements:
- No double-selling of seats.
- Exactly one successful reservation for a hot-seat concurrency storm.
- Clean HTTP 409 responses for business contention.
- Idempotent retries.
- Concurrency-safe per-user reservation limits.
- Atomic multi-seat reservations.
- Consistent seat counts after concurrent operations.
- Health/readiness endpoints.
- Prometheus-compatible metrics.
- Correlated structured request logging.
- Dockerized deployment.

## 🏗️ Architecture

~~~
Client / Burst Test
        │
        ▼
   FastAPI REST API
        │
        ├── Request Correlation ID
        ├── Idempotency
        ├── Business Validation
        ├── PostgreSQL Transactions
        └── Prometheus Metrics
        │
        ▼
    PostgreSQL
        │
        ├── Shows
        ├── Seats
        └── Reservations
~~~

### Technology Stack

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
- Docker / Docker Compose
- Prometheus client
- Pytest
- Render

## 🔐 Reservation Semantics

### No double-selling

Requested seats are locked inside a database transaction using PostgreSQL row-level locking. Seat IDs are sorted before locking so concurrent requests acquire locks in deterministic order.

### Same-user concurrency

A PostgreSQL transaction-level advisory lock is acquired for:

~~~
reservation:{show_id}:{user_id}
~~~

This serializes concurrent reservation attempts from the same user for the same show and protects per-user limits and idempotency races.

### Idempotency

Idempotency is scoped to:

~~~
(user_id, show_id, idempotency_key)
~~~

Same key + same request returns the original reservation. Same key + different seat selection returns HTTP 409. Concurrent requests using the same key create exactly one reservation.

### Per-user limit

Each show has a configurable per_user_limit. The limit is enforced transactionally, so concurrent requests cannot bypass it.

### All-or-nothing reservation

A multi-seat request is atomic. If any requested seat cannot be reserved, the complete request fails and no partial reservation is created.

### Cancellation

Cancellation locks the reservation and its seats, marks the reservation as cancelled, and returns the seats to the available state atomically.

## 📡 API Endpoints

### Service

~~~
GET /
GET /api/v1
~~~

### Shows

~~~
POST /shows
GET  /shows/{show_id}
~~~

### Reservations

~~~
POST /shows/{show_id}/reserve
POST /reservations/{reservation_id}/cancel
~~~

### Health

~~~
GET /health/live
GET /health/ready
~~~

### Observability

~~~
GET /metrics
~~~

API documentation is available at /docs and /redoc.

## 💰 Money Handling

All monetary values are stored and returned as **integer paise**.

Example: price_paise = 50000 represents ₹500.00.

No floating-point money calculations are used.

## 🧪 Concurrency Validation

The service was tested against a Dockerized FastAPI + PostgreSQL environment.

### Hot-seat storm

500 concurrent requests targeted the same seat.

~~~
Total requests: 500
confirmed: 1
SEAT_TAKEN: 499
~~~

Reconciliation:

~~~
Total seats: 100
Available: 99
Held: 0
Confirmed: 1
Sum: 100

PASS
~~~

### Idempotency storm

500 concurrent requests used the same idempotency key.

~~~
Total requests: 500
confirmed: 1
replay: 499
Unique reservation IDs: 1
~~~

Reconciliation:

~~~
Total seats: 10
Available: 9
Held: 0
Confirmed: 1
Sum: 10

PASS
~~~

### Same-user limit storm

10 concurrent requests were made by the same user with a per-user limit of 4.

~~~
Total requests: 10
confirmed: 4
PER_USER_LIMIT_EXCEEDED: 6
~~~

Reconciliation:

~~~
Total seats: 20
Available: 16
Held: 0
Confirmed: 4
Sum: 20

PASS
~~~

The core invariant is:

~~~
available + held + confirmed = total seats
~~~

## 🩺 Health Checks

Liveness: GET /health/live

Readiness: GET /health/ready

Readiness verifies database connectivity and fails closed when the database is unavailable.

## 📊 Observability

Prometheus-compatible metrics are exposed at:

https://seat-reservation-service-81no.onrender.com/metrics

Metrics include:
- Confirmed reservation counter.
- Reservation declines by reason.
- Request count.
- Request latency histogram.
- Available-seat gauge.

Structured request logging includes a correlation/request ID.

## 🐳 Run Locally

Clone:

~~~
git clone https://github.com/PiyushTiwari01/seat-reservation-service.git
cd seat-reservation-service
~~~

Start PostgreSQL:

~~~
docker compose up -d
~~~

Create a virtual environment:

Windows:
~~~
python -m venv .venv
.venv\Scripts\activate
~~~

Linux/macOS:
~~~
python3 -m venv .venv
source .venv/bin/activate
~~~

Install dependencies:

~~~
pip install -r requirements.txt
~~~

Create .env:

~~~
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/seatdb
~~~

Start API:

~~~
uvicorn app.main:app --reload
~~~

Swagger:

http://127.0.0.1:8000/docs

## 🐳 Docker

Run the full stack:

~~~
docker compose up --build
~~~

API:

http://127.0.0.1:8000

Swagger:

http://127.0.0.1:8000/docs

## 🧪 Testing

Run automated tests:

~~~
pytest -q
~~~

Run concurrency validation:

~~~
python scripts/burst.py http://127.0.0.1:8000
python scripts/idempotency_burst.py http://127.0.0.1:8000
python scripts/user_limit_burst.py http://127.0.0.1:8000
~~~

## 🔑 Example Reservation

Authentication identity is supplied through the bearer token.

~~~
POST /shows/{show_id}/reserve
Authorization: Bearer user-123
Content-Type: application/json
~~~

Request:

~~~
{
  "seats": ["A1", "A2"],
  "idempotency_key": "checkout-12345"
}
~~~

## 🚦 Expected Conflict Responses

Business contention uses HTTP 409 Conflict.

Examples:
- SEAT_TAKEN
- PER_USER_LIMIT_EXCEEDED
- IDEMPOTENCY_CONFLICT

Expected business contention is never intentionally converted into HTTP 500.

## 📦 Project Structure

~~~
seat-reservation-service/
├── app/
├── scripts/
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .gitignore
└── README.md
~~~

## 🚀 Deployment

The backend is deployed on Render with PostgreSQL. Production configuration uses the managed PostgreSQL connection string through DATABASE_URL.

The service is Docker-ready and can also be deployed to other container platforms.

## 🤖 AI Usage Disclosure

AI tools were used as an engineering assistant for scaffolding, code review, test-case generation, debugging guidance, and documentation assistance.

The implementation was reviewed and validated through API testing, Dockerized execution, automated tests, and concurrent burst tests.

The key engineering decisions around transaction boundaries, seat locking, advisory locking, idempotency, per-user concurrency, database consistency, and conflict handling were explicitly validated against the assignment requirements.

## 👤 Author

**Piyush Tiwari**

Backend / Full Stack Developer

GitHub: https://github.com/PiyushTiwari01

## 📌 Submission

**Repository:** https://github.com/PiyushTiwari01/seat-reservation-service

**Live API:** https://seat-reservation-service-81no.onrender.com

**Swagger:** https://seat-reservation-service-81no.onrender.com/docs

**Metrics:** https://seat-reservation-service-81no.onrender.com/metrics

**Readiness:** https://seat-reservation-service-81no.onrender.com/health/ready
