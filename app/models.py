import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from .database import Base


def uuid_str():
    return str(uuid.uuid4())


class Show(Base):
    __tablename__ = "shows"

    id = Column(String(36), primary_key=True, default=uuid_str)
    name = Column(String(255), nullable=False)
    price_paise = Column(Integer, nullable=False)
    per_user_limit = Column(Integer, nullable=False, default=4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Seat(Base):
    __tablename__ = "seats"

    id = Column(String(36), primary_key=True, default=uuid_str)
    show_id = Column(String(36), ForeignKey("shows.id"), nullable=False)
    seat_number = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="available")
    reservation_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("show_id", "seat_number", name="uq_show_seat"),
    )


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String(36), primary_key=True, default=uuid_str)
    show_id = Column(String(36), ForeignKey("shows.id"), nullable=False)
    user_id = Column(String(255), nullable=False)
    amount_paise = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="confirmed")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReservationSeat(Base):
    __tablename__ = "reservation_seats"

    id = Column(String(36), primary_key=True, default=uuid_str)
    reservation_id = Column(
        String(36), ForeignKey("reservations.id"), nullable=False
    )
    seat_id = Column(String(36), ForeignKey("seats.id"), nullable=False)
    seat_number = Column(String(50), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "reservation_id", "seat_id", name="uq_reservation_seat"
        ),
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id = Column(String(36), primary_key=True, default=uuid_str)
    user_id = Column(String(255), nullable=False)
    show_id = Column(String(36), ForeignKey("shows.id"), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False)
    reservation_id = Column(String(36), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "show_id",
            "idempotency_key",
            name="uq_idempotency",
        ),
    )
