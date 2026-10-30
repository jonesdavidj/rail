"""Bounded time-window paging with an absolute time/service boundary."""

import base64
import binascii
from datetime import datetime, timedelta

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from app.config import Route
from app.journeys import CANCELLED, is_fast, journey_minutes
from app.models import BoardPage, NormalisedBoard
from app.normalise import LONDON, departure_datetime
from app.providers import DepartureProvider
from app.rail_data import BOARD_ROWS

MIN_OFFSET = -60
MAX_OFFSET = 119
EARLIER_OFFSET = -45


class PageCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor: AwareDatetime
    boundary: AwareDatetime
    service_id: str = Field(max_length=512)
    origin: str = Field(pattern=r"^[A-Z]{3}$")
    destination: str = Field(pattern=r"^[A-Z]{3}$")

    def encode(self) -> str:
        return base64.urlsafe_b64encode(self.model_dump_json().encode()).decode().rstrip("=")


def read_cursor(value: str, route: Route, now: datetime) -> PageCursor:
    try:
        body = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        cursor = PageCursor.model_validate_json(body)
    except (ValueError, binascii.Error, ValidationError):
        raise ValueError("Invalid page cursor; return to next departures.") from None
    minute = now.astimezone(LONDON).replace(second=0, microsecond=0)
    if (
        (cursor.origin, cursor.destination) != (route.origin, route.destination)
        or not minute - timedelta(minutes=15) <= cursor.anchor <= minute
        or not cursor.anchor - timedelta(minutes=60)
        <= cursor.boundary
        < cursor.anchor + timedelta(minutes=120)
    ):
        raise ValueError("Page expired or route changed; return to next departures.")
    return cursor


def cursor_offset(cursor: PageCursor, now: datetime) -> int:
    minute = now.astimezone(LONDON).replace(second=0, microsecond=0)
    offset = int((cursor.boundary.timestamp() - minute.timestamp()) // 60)
    if not MIN_OFFSET <= offset <= MAX_OFFSET:
        raise ValueError("Page is outside the feed window; return to next departures.")
    return offset


def page_board(
    board: NormalisedBoard,
    route: Route,
    offset: int,
    provider: DepartureProvider,
    now: datetime | None = None,
    cursor: PageCursor | None = None,
    fast_only: bool = False,
) -> BoardPage:
    minute = (now or board.generated_at).astimezone(LONDON).replace(second=0, microsecond=0)
    anchor = cursor.anchor if cursor else minute
    horizon = anchor + timedelta(minutes=120)
    threshold = max(offset, route.min_departure_minutes) if offset >= 0 else offset
    lower = minute + timedelta(minutes=threshold)
    candidates = []
    for service in board.services:
        departure = departure_datetime(service.planned, minute)
        if departure >= horizon:
            continue
        if cursor:
            if (departure, service.id) <= (cursor.boundary, cursor.service_id):
                continue
        elif departure < lower:
            continue
        candidates.append(
            service.model_copy(
                update={
                    "is_fast": is_fast(service, route),
                    "journey_minutes": journey_minutes(service),
                    "is_quickest": False,
                }
            )
        )
    examined = []
    shown = []
    for service in candidates:
        if fast_only:
            # Leave overflow fast rows unconsumed; consume intervening slow rows too.
            if service.is_fast and len(shown) == route.page_size:
                break
            examined.append(service)
            if service.is_fast:
                shown.append(service)
        else:
            if len(shown) == route.page_size:
                break
            examined.append(service)
            shown.append(service)
    eligible = [
        service
        for service in shown
        if service.status not in CANCELLED and service.journey_minutes is not None
    ]
    if eligible:
        quickest = min(eligible, key=lambda service: service.journey_minutes)
        shown = [
            service.model_copy(update={"is_quickest": service is quickest}) for service in shown
        ]
    next_cursor = None
    next_offset = None
    if examined:
        last = examined[-1]
        boundary = departure_datetime(last.planned, minute)
        # A full upstream response is a row limit, not proof that the timetable ends.
        capped = len(board.services) >= BOARD_ROWS and (
            departure_datetime(board.services[-1].planned, minute) < horizon
        )
        more = len(candidates) > len(examined) or capped or fast_only
        if more and boundary < horizon:
            next_cursor = PageCursor(
                anchor=anchor,
                boundary=boundary,
                service_id=last.id,
                origin=route.origin,
                destination=route.destination,
            ).encode()
            # Re-fetch the boundary minute inclusively; the cursor removes seen rows.
            next_offset = max(MIN_OFFSET, min(MAX_OFFSET, last.in_min))
    elif fast_only:
        # A repeated boundary/empty response must still make time progress.
        boundary = (
            (cursor.boundary + timedelta(minutes=1)) if cursor else lower + timedelta(minutes=1)
        )
        if len(board.services) < BOARD_ROWS:
            boundary = max(boundary, horizon - timedelta(minutes=1))
        if boundary < horizon:
            next_cursor = PageCursor(
                anchor=anchor,
                boundary=boundary,
                service_id="",
                origin=route.origin,
                destination=route.destination,
            ).encode()
            next_offset = max(
                MIN_OFFSET, min(MAX_OFFSET, int((boundary.timestamp() - minute.timestamp()) // 60))
            )
    return BoardPage(
        generated_at=board.generated_at,
        services=shown,
        messages=board.messages,
        services_available=board.services_available,
        route=route.id,
        title=route.label,
        mode=provider.mode,
        demo=provider.mode == "demo",
        offset=offset,
        next_offset=next_offset,
        next_cursor=next_cursor,
        has_next=next_cursor is not None,
        earlier_offset=EARLIER_OFFSET if offset >= 0 else None,
        fast_only=fast_only,
        fast_count=sum(service.is_fast for service in shown),
        total_count=len(examined),
    )
