"""On-demand Home Assistant adapter; no scheduler, credentials or HA dependencies."""

import logging
import math
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import Route, RouteID
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


class Summary(BaseModel):
    route: str
    as_of: datetime
    generated_at: datetime
    walking_minutes: int
    next_departure: NextDeparture | None
    cancelled_count: int
    delayed_count: int
    services: list[SelectedService]
    demo: bool = False
    stale: bool = False
    complete: bool = True


def summarise(services: list[Service], route: Route, now: datetime) -> Summary:
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
            SelectedService(id=identity, planned=planned, status=service.status)
            for planned, identity, service in window
        ],
    )


def summary_router(
    store: RouteStore, provider: DepartureProvider, clock: Callable[[], datetime]
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/summary", response_model=Summary)
    def summary(route: Annotated[RouteID, Query()]) -> Summary | JSONResponse:
        config = next((item for item in store.snapshot().config.routes if item.id == route), None)
        if config is None:
            raise HTTPException(404, "Unknown route")
        started = clock()
        end = started.astimezone(LONDON).replace(second=0, microsecond=0) + timedelta(minutes=120)
        deadline = time.monotonic() + 20
        collected: dict[str, Service] = {}
        generated = started
        stale, complete, offset = False, False, 0
        try:
            # Bound work even if the feed saturates one minute or changes during the walk.
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
                    (boundary.timestamp() - clock().replace(second=0, microsecond=0).timestamp())
                    // 60
                )
                if not -60 <= offset <= 119:
                    break
            return summarise(list(collected.values()), config, started).model_copy(
                update={
                    "generated_at": generated,
                    "demo": provider.mode == "demo",
                    "stale": stale,
                    "complete": complete,
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
