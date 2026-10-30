"""Small route-specific classifications, independent of feed transport and UI."""

from app.config import Route
from app.models import Service

CANCELLED = {"cancelled", "part_cancelled"}


def is_fast(service: Service, route: Route) -> bool:
    return (
        service.status not in CANCELLED
        and service.service_type == "train"
        and service.stop_count is not None
        and service.stop_count <= route.fast_max_stops
    )


def journey_minutes(service: Service) -> int | None:
    arrival = service.arrival
    if not arrival:
        return None
    departure_expected = service.expected or (
        service.planned if service.status == "on_time" else None
    )
    arrival_expected = arrival.expected or (arrival.planned if arrival.state == "on_time" else None)
    if departure_expected and arrival_expected:
        start, end = departure_expected, arrival_expected
    elif arrival.planned:
        start, end = service.planned, arrival.planned
    else:
        return None
    start_minute = int(start[:2]) * 60 + int(start[3:])
    end_minute = int(end[:2]) * 60 + int(end[3:])
    return (end_minute - start_minute) % 1440
