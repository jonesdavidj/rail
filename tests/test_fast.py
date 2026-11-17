"""Only the three requested fast/journey regressions."""

from datetime import datetime

from app.config import defaults
from app.journeys import is_fast, journey_minutes
from app.models import Arrival, NormalisedBoard, Service
from app.paging import cursor_offset, page_board, read_cursor
from app.providers import DemoProvider


def test_fast_classification_boundary() -> None:
    route = defaults().routes[0]
    services = [
        Service(id=str(n), planned="18:00", in_min=0, status="on_time", stop_count=n)
        for n in (0, 1, 2)
    ]
    assert [is_fast(service, route) for service in services] == [True, True, False]
    assert [
        is_fast(service, route.model_copy(update={"fast_max_stops": 0})) for service in services
    ] == [True, False, False]
    assert not is_fast(services[0].model_copy(update={"status": "cancelled"}), route)


def test_filtered_cursor_never_skips_fast_services(now: datetime) -> None:
    route = defaults().routes[0].model_copy(update={"page_size": 2})
    provider = DemoProvider()
    services = [
        Service(
            id=str(i),
            planned=f"18:{i + 1:02d}",
            in_min=i + 1,
            status="on_time",
            stop_count=1 if i in (10, 11, 18, 19) else 3,
        )
        for i in range(20)
    ]
    offset, cursor, seen = 0, None, []
    for index in range(8):
        board = NormalisedBoard(
            generated_at=now, services=[s for s in services if s.in_min >= offset][:10], messages=[]
        )
        page = page_board(board, route, offset, provider, now, cursor, fast_only=True)
        seen.extend(s.id for s in page.services)
        if index == 0:
            assert not page.services and page.has_next and page.next_offset == 10
        if index == 1:
            assert page.next_offset == 18  # Consumed slow rows after the last displayed fast train.
        if not page.has_next:
            break
        cursor = read_cursor(page.next_cursor, route, now)
        offset = cursor_offset(cursor, now)
    assert seen == ["10", "11", "18", "19"]
    assert not page.has_next


def test_journey_time_across_midnight() -> None:
    service = Service(
        id="midnight",
        planned="23:50",
        expected="23:57",
        in_min=0,
        status="late",
        arrival=Arrival(planned="00:10", expected="00:22", state="estimated"),
    )
    assert journey_minutes(service) == 25
    assert journey_minutes(service.model_copy(update={"expected": None})) == 20


def test_fast_filter_keeps_cancellations_and_pages_them(now: datetime) -> None:
    route = defaults().routes[0].model_copy(update={"page_size": 1})
    board = NormalisedBoard(
        generated_at=now,
        messages=[],
        services=[
            Service(
                id=str(i),
                planned=f"18:0{i + 1}",
                in_min=i + 1,
                status=status,
                stop_count=stops,
            )
            for i, (status, stops) in enumerate(
                [
                    ("cancelled", 1),
                    ("cancelled", 3),
                    ("part_cancelled", 0),
                    ("on_time", 1),
                ]
            )
        ],
    )
    first = page_board(board, route, 0, DemoProvider(), now, fast_only=True)
    assert [s.id for s in first.services] == ["0"]
    assert not first.services[0].is_fast and not first.services[0].is_quickest
    cursor = read_cursor(first.next_cursor, route, now)
    second = page_board(
        board, route, cursor_offset(cursor, now), DemoProvider(), now, cursor, fast_only=True
    )
    assert [s.id for s in second.services] == ["2"]
    assert second.services[0].status == "part_cancelled"
    assert second.has_next
