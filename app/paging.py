"""Bounded time-window paging with an absolute time/service boundary."""

import base64
import binascii
from datetime import datetime, timedelta

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from app.config import Route
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
    service_id: str = Field(min_length=1, max_length=512)
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
        candidates.append(service)
    shown = candidates[: route.page_size]
    next_cursor = None
    next_offset = None
    if shown:
        last = shown[-1]
        boundary = departure_datetime(last.planned, minute)
        # A full upstream response is a row limit, not proof that the timetable ends.
        capped = len(board.services) >= BOARD_ROWS and (
            departure_datetime(board.services[-1].planned, minute) < horizon
        )
        more = len(candidates) > len(shown) or capped
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
    )
