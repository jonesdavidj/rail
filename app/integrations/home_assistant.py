"""On-demand Home Assistant adapter; no scheduler, credentials or HA dependencies."""

import logging
import math
import time
from _thread import LockType
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import Route, RouteID
from app.journeys import is_fast, journey_minutes
from app.models import Service, Status
from app.normalise import LONDON, departure_datetime, minutes_between, normalise_board
from app.providers import DepartureProvider
from app.rail_data import BOARD_ROWS, ProviderError
from app.routes import RouteStore

logger = logging.getLogger(__name__)
CANCELLED = {"cancelled", "part_cancelled"}


class SelectedService(BaseModel):
    id: str
    planned: datetime
    status: Status


class NextDeparture(SelectedService):
    expected: datetime | None
    minutes_until_departure: int | None
    platform: str
    carriage_count: int | None


class SummaryStop(BaseModel):
    name: str
    crs: str
    planned: datetime | None
    expected: datetime | None
    cancelled: bool


class SummaryService(SelectedService):
    expected: datetime | None
    delay_minutes: int | None
    platform: str | None
    carriage_count: int | None
    destination: str
    arrival_planned: datetime | None
    arrival_expected: datetime | None
    journey_minutes: int | None
    stop_count: int | None
    fast: bool
    stops: list[SummaryStop] | None = None  # Only set (and sent) when ?stops=1.


class Summary(BaseModel):
    route: str
    as_of: datetime
    generated_at: datetime
    walking_minutes: int
    next_departure: NextDeparture | None
    cancelled_count: int
    delayed_count: int
    services: list[SummaryService]
    demo: bool = False
    stale: bool = False
    complete: bool = True


def clock_after(value: str, reference: datetime) -> datetime:
    minutes = int(value[:2]) * 60 + int(value[3:])
    return reference + timedelta(minutes=(minutes - reference.hour * 60 - reference.minute) % 1440)


def summary_stops(service: Service, planned: datetime) -> list[SummaryStop]:
    """Calling points up to the route destination, each placed after the previous one."""
    stops: list[SummaryStop] = []
    reference = planned
    for stop in service.stops:
        stop_planned = stop_expected = None
        if stop.planned:
            stop_planned = reference = clock_after(stop.planned, reference)
            if stop.expected:
                stop_expected = stop_planned + timedelta(
                    minutes=minutes_between(stop.planned, stop.expected)
                )
            elif stop.state in {"on_time", "actual"}:
                stop_expected = stop_planned
        stops.append(
            SummaryStop(
                name=stop.name,
                crs=stop.crs,
                planned=stop_planned.astimezone(UTC) if stop_planned else None,
                expected=stop_expected.astimezone(UTC) if stop_expected else None,
                cancelled=stop.cancelled,
            )
        )
    return stops


def service_summary(
    service: Service, route: Route, planned: datetime, with_stops: bool = False
) -> SummaryService:
    expected = (
        planned + timedelta(minutes=minutes_between(service.planned, service.expected))
        if service.expected
        else planned
        if service.status == "on_time"
        else None
    )
    arrival_planned = arrival_expected = None
    arrival = service.arrival
    if arrival:
        if arrival.planned:
            arrival_planned = clock_after(arrival.planned, planned)
        if not arrival.cancelled:
            if arrival.expected:
                if arrival_planned:
                    arrival_expected = arrival_planned + timedelta(
                        minutes=minutes_between(arrival.planned, arrival.expected)
                    )
                elif expected:
                    arrival_expected = clock_after(arrival.expected, expected)
            elif arrival.state in {"on_time", "actual"}:
                arrival_expected = arrival_planned
    return SummaryService(
        id=service.id,
        planned=planned,
        status=service.status,
        expected=expected,
        delay_minutes=0 if service.status == "on_time" else service.delay_min,
        platform=None if service.platform.casefold() in {"", "tbc"} else service.platform,
        carriage_count=service.length,
        destination=service.destination,
        arrival_planned=arrival_planned.astimezone(UTC) if arrival_planned else None,
        arrival_expected=arrival_expected.astimezone(UTC) if arrival_expected else None,
        journey_minutes=journey_minutes(service),
        stop_count=service.stop_count,
        fast=is_fast(service, route),
        **({"stops": summary_stops(service, planned)} if with_stops else {}),
    )


def summarise(
    services: list[Service], route: Route, now: datetime, n: int = 7, with_stops: bool = False
) -> Summary:
    """Count the whole scheduled window; choose the next usable board-order train."""
    minute = now.astimezone(LONDON).replace(second=0, microsecond=0)
    window = sorted(
        (
            (departure_datetime(service.planned, minute), service.id, service)
            for service in services
            if 0 <= (departure_datetime(service.planned, minute) - minute).total_seconds() < 7200
        ),
        key=lambda item: (item[0], item[1]),
    )
    next_departure = None
    for planned, _, service in window:
        if service.status in CANCELLED or planned < minute + timedelta(
            minutes=route.min_departure_minutes
        ):
            continue
        expected = (
            planned + timedelta(minutes=minutes_between(service.planned, service.expected))
            if service.expected
            else planned
            if service.status == "on_time"
            else None
        )
        next_departure = NextDeparture(
            id=service.id,
            planned=planned,
            expected=expected,
            minutes_until_departure=max(0, math.ceil((expected - now).total_seconds() / 60))
            if expected
            else None,
            status=service.status,
            platform=service.platform,
            carriage_count=service.length,
        )
        break
    return Summary(
        route=route.id,
        as_of=now,
        generated_at=now,
        walking_minutes=route.min_departure_minutes,
        next_departure=next_departure,
        cancelled_count=sum(service.status in CANCELLED for _, _, service in window),
        delayed_count=sum(service.status in {"late", "delayed"} for _, _, service in window),
        services=[
            service_summary(service, route, planned, with_stops)
            for planned, _, service in window
            if planned >= minute + timedelta(minutes=route.min_departure_minutes)
        ][:n],
    )


@dataclass(frozen=True)
class ScannedBoard:
    services: list[Service]
    generated_at: datetime
    stale: bool
    complete: bool


def scan_window(
    config: Route, provider: DepartureProvider, clock: Callable[[], datetime], started: datetime
) -> ScannedBoard:
    end = started.astimezone(LONDON).replace(second=0, microsecond=0) + timedelta(minutes=120)
    deadline = time.monotonic() + 20
    collected: dict[str, Service] = {}
    generated = started
    stale, complete, offset = False, False, 0
    for _ in range(16):
        if time.monotonic() >= deadline:
            break
        moment = clock()
        result = provider.board(config, offset, moment)
        board = normalise_board(result.raw, config.destination, moment)
        generated = min(generated, board.generated_at)
        stale = stale or result.stale
        previous = len(collected)
        collected.update((service.id, service) for service in board.services)
        if (
            len(board.services) < BOARD_ROWS
            or departure_datetime(board.services[-1].planned, moment) >= end
        ):
            complete = board.services_available
            break
        if len(collected) == previous:
            break
        boundary = departure_datetime(board.services[-1].planned, moment)
        offset = int(
            (boundary.timestamp() - clock().replace(second=0, microsecond=0).timestamp()) // 60
        )
        if not -60 <= offset <= 119:
            break
    return ScannedBoard(list(collected.values()), generated, stale, complete)


def summary_router(
    store: RouteStore,
    provider: DepartureProvider,
    clock: Callable[[], datetime],
    cache_ttl: int = 30,
) -> APIRouter:
    router = APIRouter()
    cache: dict[tuple[str, str, str], tuple[float, ScannedBoard]] = {}
    locks: dict[tuple[str, str, str], LockType] = {}
    guard = Lock()

    @router.get("/api/summary", response_model=Summary, response_model_exclude_unset=True)
    def summary(
        route: Annotated[RouteID, Query()],
        n: Annotated[int, Query(ge=1, le=10)] = 7,
        stops: Annotated[bool, Query()] = False,
    ) -> Summary | JSONResponse:
        config = next((item for item in store.snapshot().config.routes if item.id == route), None)
        if config is None:
            raise HTTPException(404, "Unknown route")
        started = clock()
        key = config.id, config.origin, config.destination
        try:
            with guard:
                lock = locks.setdefault(key, Lock())
            # Cache the scan, not its projection: n/config changes and ETA countdowns
            # stay local, including when another minute starts while this cache is fresh.
            with lock:
                entry = cache.get(key)
                if entry is None or time.monotonic() - entry[0] >= cache_ttl:
                    scanned = scan_window(config, provider, clock, started)
                    with guard:
                        cache[key] = time.monotonic(), scanned
                        if len(cache) > 64:
                            cache.pop(next(iter(cache)))
                else:
                    scanned = entry[1]
            return summarise(scanned.services, config, started, n, stops).model_copy(
                update={
                    "generated_at": scanned.generated_at,
                    "demo": provider.mode == "demo",
                    "stale": scanned.stale,
                    "complete": scanned.complete,
                }
            )
        except ProviderError as error:
            logger.warning("summary_provider_error", extra={"fields": {"code": error.code}})
            return JSONResponse(
                {"error": str(error), "error_code": error.code, "stale": False},
                status_code=error.status,
                headers={"Retry-After": str(error.retry_after)},
            )
        except ValueError:
            raise HTTPException(502, "Provider returned an invalid board") from None

    return router
