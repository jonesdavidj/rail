"""Prototype-compatible relative time-window paging, with walking-time filtering."""

from app.config import Route
from app.models import BoardPage, NormalisedBoard
from app.providers import DepartureProvider

MIN_OFFSET = -60
MAX_OFFSET = 119
EARLIER_OFFSET = -45


def page_board(
    board: NormalisedBoard,
    route: Route,
    offset: int,
    provider: DepartureProvider,
) -> BoardPage:
    # Walking time applies to the live/future board; Earlier is deliberately historical.
    threshold = max(offset, route.min_departure_minutes) if offset >= 0 else offset
    candidates = [service for service in board.services if service.in_min >= threshold]
    shown = candidates[: route.page_size]
    next_offset = None
    if shown and len(candidates) > route.page_size:
        candidate = max(offset + 1, shown[-1].in_min + 1)
        if candidate <= MAX_OFFSET:
            next_offset = candidate
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
        has_next=next_offset is not None,
        earlier_offset=EARLIER_OFFSET if offset >= 0 else None,
    )
