# Engineering Write-up

## 1. Atomic reservation decision

Seat rows are stored in PostgreSQL and reservation requests run inside a database transaction.

Requested seats are normalized and sorted before they are locked. PostgreSQL `SELECT ... FOR UPDATE` row locks serialize competing transactions for the same seat.

The service verifies that every requested seat is `available` while the locks are held, creates the reservation, changes the seats to `confirmed`, records the reservation-seat mapping, and stores the idempotency record before committing.

Therefore, two concurrent requests cannot both observe and commit the same available seat.

## 2. Multi-seat behavior

The API uses all-or-nothing semantics. If any requested seat is unavailable, the entire reservation is declined with HTTP 409.

Seat identifiers are sorted before locking to provide deterministic lock ordering and reduce deadlock risk.

## 3. Idempotency

Idempotency records are stored in PostgreSQL with a unique constraint over:

`(user_id, show_id, idempotency_key)`

The normalized requested seat set is hashed and stored.

A retry using the same key and same request returns the original reservation. Reusing the key with a different seat set returns HTTP 409.

The database unique constraint remains the final concurrency guard if identical requests arrive simultaneously.

## 4. Per-user limit

The service counts the user's active confirmed seats while the reservation transaction is executing. The requested seats are then checked against `per_user_limit`.

## 5. Cancellation

Cancellation is explicit. Only the reservation owner can cancel it. The reservation and its seat rows are locked, the reservation becomes `cancelled`, and its confirmed seats become `available` in the same transaction.

## 6. Consistency vs availability

Seat reservation is consistency-first. If the database cannot be reached, the service should not accept a booking that cannot be durably committed. During normal contention, expected domain declines are represented as 409 responses rather than server errors.

## 7. Observability

The service exposes:

- liveness and readiness endpoints
- Prometheus counters for confirmed reservations
- decline counters by reason
- available-seat gauge
- reservation latency histogram
- structured JSON logs
- request IDs

A production deployment should alert on sustained 5xx responses, readiness failures, database connection failures, abnormal reservation latency, and any reconciliation mismatch.

## 8. AI usage

AI tools were used for scaffolding, code review, test-case generation, and documentation assistance. The candidate is responsible for reviewing, understanding, and validating all generated code, especially database transaction behavior and concurrency guarantees.

## 9. Next steps

For a larger production system I would consider database migrations, stronger authentication, distributed rate limiting, tracing, automated reconciliation jobs, database connection-pool tuning, and a dedicated load-test environment.
