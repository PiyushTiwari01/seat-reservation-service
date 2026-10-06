import hashlib
import json
import time
import uuid
from contextlib import contextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from prometheus_client import generate_latest
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import get_current_user
from .database import Base, engine, get_db
from .metrics import (
    reservation_latency,
    reservation_requests,
    reservations_confirmed,
    reservations_declined,
    seats_available,
)
from .models import IdempotencyKey, Reservation, ReservationSeat, Seat, Show
from .observability import log_event, request_id_from
from .schemas import CancelResponse, CreateShowRequest, ReserveRequest

app = FastAPI(
    title="Seat Reservation at Scale",
    version="1.0.0",
)

Base.metadata.create_all(bind=engine)


def normalized_hash(seats: list[str]) -> str:
    normalized = sorted(set(seats))
    raw = json.dumps({"seats": normalized}, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def reservation_response(db: Session, reservation: Reservation):
    seat_rows = (
        db.query(ReservationSeat)
        .filter(ReservationSeat.reservation_id == reservation.id)
        .order_by(ReservationSeat.seat_number)
        .all()
    )
    return {
        "reservation_id": reservation.id,
        "show_id": reservation.show_id,
        "user_id": reservation.user_id,
        "seats": [row.seat_number for row in seat_rows],
        "amount_paise": reservation.amount_paise,
        "status": reservation.status,
    }


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request_id_from(request)
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


@app.get("/health/live")
def liveness():
    return {"status": "ok"}


@app.get("/health/ready")
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "database": "unavailable"},
        )


@app.get("/metrics")
def metrics():
    return Response(
        content=generate_latest(),
        media_type="text/plain; version=0.0.4",
    )


@app.post("/shows", status_code=201)
def create_show(
    request: CreateShowRequest,
    db: Session = Depends(get_db),
):
    seats = [s.strip() for s in request.seats]

    if any(not s for s in seats):
        raise HTTPException(status_code=400, detail="Seat names cannot be empty")

    if len(set(seats)) != len(seats):
        raise HTTPException(status_code=400, detail="Duplicate seat numbers are not allowed")

    show = Show(
        name=request.name,
        price_paise=request.price_paise,
        per_user_limit=request.per_user_limit,
    )
    db.add(show)
    db.flush()

    for seat_number in seats:
        db.add(
            Seat(
                show_id=show.id,
                seat_number=seat_number,
                status="available",
            )
        )

    db.commit()

    seats_available.set(len(seats))

    return {
        "id": show.id,
        "name": show.name,
        "price_paise": show.price_paise,
        "per_user_limit": show.per_user_limit,
        "seats": [
            {"seat": seat_number, "status": "available"}
            for seat_number in seats
        ],
    }


@app.get("/shows/{show_id}")
def get_show(
    show_id: str,
    db: Session = Depends(get_db),
):
    show = db.query(Show).filter(Show.id == show_id).first()
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")

    seats = (
        db.query(Seat)
        .filter(Seat.show_id == show_id)
        .order_by(Seat.seat_number)
        .all()
    )

    counts = {"available": 0, "held": 0, "confirmed": 0}
    result = []

    for seat in seats:
        counts[seat.status] = counts.get(seat.status, 0) + 1
        result.append({"seat": seat.seat_number, "status": seat.status})

    seats_available.set(counts.get("available", 0))

    return {
        "show_id": show.id,
        "name": show.name,
        "price_paise": show.price_paise,
        "per_user_limit": show.per_user_limit,
        "total_seats": len(seats),
        "counts": counts,
        "seats": result,
    }


@app.post("/shows/{show_id}/reserve", status_code=201)
def reserve(
    show_id: str,
    request: ReserveRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    started = time.perf_counter()
    reservation_requests.inc()
    rid = http_request.state.request_id

    seats_requested = [s.strip() for s in request.seats]
    seats_requested = sorted(set(seats_requested))

    if not seats_requested or any(not s for s in seats_requested):
        reservations_declined.labels("invalid_request").inc()
        raise HTTPException(status_code=422, detail="At least one valid seat is required")

    request_hash = normalized_hash(seats_requested)

    # Serialize all reservations for the same user + show.
    # This makes the per-user limit and idempotency check concurrency-safe.
    user_show_lock_key = f"reservation:{show_id}:{user_id}"

    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": user_show_lock_key},
    )

    # Idempotency is checked before the transaction. The unique DB constraint
    # is the final arbiter under concurrent duplicate requests.

    existing = (
        db.query(IdempotencyKey)
        .filter(
            IdempotencyKey.user_id == user_id,
            IdempotencyKey.show_id == show_id,
            IdempotencyKey.idempotency_key == request.idempotency_key,
        )
        .first()
    )

    if existing:
        if existing.request_hash != request_hash:
            reservations_declined.labels("idempotency_conflict").inc()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "IDEMPOTENCY_KEY_REUSED",
                    "message": "Same idempotency key was used with a different request body",
                    "request_id": rid,
                },
            )

        reservation = (
            db.query(Reservation)
            .filter(Reservation.id == existing.reservation_id)
            .first()
        )
        reservations_declined.labels("idempotent_replay").inc()

        if not reservation:
            raise HTTPException(status_code=409, detail="Idempotency record is inconsistent")

        response = reservation_response(db, reservation)
        response["idempotent_replay"] = True
        return response

    show = db.query(Show).filter(Show.id == show_id).first()
    if not show:
        reservations_declined.labels("show_not_found").inc()
        raise HTTPException(status_code=404, detail="Show not found")

    try:
        # Lock requested seats in deterministic order. PostgreSQL row locks
        # serialize concurrent attempts for the same hot seat.
        seat_rows = (
            db.query(Seat)
            .filter(
                Seat.show_id == show_id,
                Seat.seat_number.in_(seats_requested),
            )
            .order_by(Seat.seat_number)
            .with_for_update()
            .all()
        )

        if len(seat_rows) != len(seats_requested):
            reservations_declined.labels("seat_not_found").inc()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "SEAT_NOT_FOUND",
                    "message": "One or more requested seats do not exist",
                    "request_id": rid,
                },
            )

        unavailable = [
            seat.seat_number
            for seat in seat_rows
            if seat.status != "available"
        ]

        if unavailable:
            db.rollback()
            reservations_declined.labels("seat_taken").inc()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "SEAT_TAKEN",
                    "message": "One or more requested seats are not available",
                    "seats": unavailable,
                    "request_id": rid,
                },
            )

        # Count only active confirmed seats while holding the requested rows.
        user_seat_count = (
            db.query(func.count(ReservationSeat.id))
            .join(
                Reservation,
                Reservation.id == ReservationSeat.reservation_id,
            )
            .filter(
                Reservation.show_id == show_id,
                Reservation.user_id == user_id,
                Reservation.status == "confirmed",
            )
            .scalar()
            or 0
        )

        if user_seat_count + len(seats_requested) > show.per_user_limit:
            db.rollback()
            reservations_declined.labels("per_user_limit").inc()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PER_USER_LIMIT_EXCEEDED",
                    "message": "User has reached the maximum number of seats for this show",
                    "limit": show.per_user_limit,
                    "request_id": rid,
                },
            )

        reservation = Reservation(
            show_id=show_id,
            user_id=user_id,
            amount_paise=show.price_paise * len(seats_requested),
            status="confirmed",
        )
        db.add(reservation)
        db.flush()

        for seat in seat_rows:
            seat.status = "confirmed"
            seat.reservation_id = reservation.id
            db.add(
                ReservationSeat(
                    reservation_id=reservation.id,
                    seat_id=seat.id,
                    seat_number=seat.seat_number,
                )
            )

        idem = IdempotencyKey(
            user_id=user_id,
            show_id=show_id,
            idempotency_key=request.idempotency_key,
            request_hash=request_hash,
            reservation_id=reservation.id,
        )
        db.add(idem)

        try:
            db.commit()
        except IntegrityError:
            # Another concurrent request won the same idempotency key.
            db.rollback()

            existing = (
                db.query(IdempotencyKey)
                .filter(
                    IdempotencyKey.user_id == user_id,
                    IdempotencyKey.show_id == show_id,
                    IdempotencyKey.idempotency_key == request.idempotency_key,
                )
                .first()
            )

            if existing and existing.request_hash == request_hash:
                existing_reservation = (
                    db.query(Reservation)
                    .filter(Reservation.id == existing.reservation_id)
                    .first()
                )
                if existing_reservation:
                    reservations_declined.labels("idempotent_replay").inc()
                    response = reservation_response(db, existing_reservation)
                    response["idempotent_replay"] = True
                    return response

            raise HTTPException(status_code=409, detail="Idempotency conflict")

        reservations_confirmed.inc()

        response = reservation_response(db, reservation)
        log_event(
            "reservation_confirmed",
            rid,
            user_id=user_id,
            show_id=show_id,
            reservation_id=reservation.id,
            seats=seats_requested,
        )
        return response

    finally:
        reservation_latency.observe(time.perf_counter() - started)


@app.post("/reservations/{reservation_id}/cancel", response_model=CancelResponse)
def cancel_reservation(
    reservation_id: str,
    http_request: Request,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    rid = http_request.state.request_id

    reservation = (
        db.query(Reservation)
        .filter(Reservation.id == reservation_id)
        .with_for_update()
        .first()
    )

    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    if reservation.user_id != user_id:
        raise HTTPException(status_code=403, detail="You can only cancel your own reservation")

    if reservation.status == "cancelled":
        return {
            "reservation_id": reservation.id,
            "status": "cancelled",
        }

    seats = (
        db.query(Seat)
        .filter(Seat.reservation_id == reservation.id)
        .order_by(Seat.seat_number)
        .with_for_update()
        .all()
    )

    reservation.status = "cancelled"

    for seat in seats:
        # Do not resurrect a seat that somehow points to a different reservation.
        if seat.reservation_id == reservation.id and seat.status == "confirmed":
            seat.status = "available"
            seat.reservation_id = None

    db.commit()

    available = (
        db.query(Seat)
        .filter(
            Seat.show_id == reservation.show_id,
            Seat.status == "available",
        )
        .count()
    )
    seats_available.set(available)

    log_event(
        "reservation_cancelled",
        rid,
        user_id=user_id,
        reservation_id=reservation.id,
    )

    return {
        "reservation_id": reservation.id,
        "status": "cancelled",
    }
