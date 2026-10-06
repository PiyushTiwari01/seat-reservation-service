from prometheus_client import Counter, Gauge, Histogram

reservations_confirmed = Counter(
    "reservations_confirmed_total",
    "Total confirmed reservations",
)

reservations_declined = Counter(
    "reservations_declined_total",
    "Total declined reservation attempts",
    ["reason"],
)

reservation_requests = Counter(
    "reservation_requests_total",
    "Total reservation requests",
)

reservation_latency = Histogram(
    "reservation_latency_seconds",
    "Reservation request latency",
)

seats_available = Gauge(
    "seats_available",
    "Number of currently available seats",
)
