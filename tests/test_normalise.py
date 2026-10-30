"""Ported prototype behaviours plus malformed-data and grouping regression cases."""

from datetime import UTC, datetime

import pytest

from app.models import Service
from app.normalise import Raw, clock, normalise_board, normalise_service, positive_int, time_state


def cp(crs: str = "WAT", **changes: object) -> Raw:
    return {
        "locationName": "London Waterloo",
        "crs": crs,
        "st": "18:22",
        "et": "On time",
        **changes,
    }


def svc(**changes: object) -> Raw:
    return {
        "serviceID": "id",
        "std": "18:05",
        "etd": "On time",
        "platform": "3",
        "operator": "South Western Railway",
        "operatorCode": "SW",
        "origin": [{"locationName": "Surbiton", "crs": "SUR"}],
        "destination": [{"locationName": "London Waterloo", "crs": "WAT"}],
        "subsequentCallingPoints": [{"callingPoint": [cp("CLJ"), cp()]}],
        **changes,
    }


def one(now: datetime, **changes: object) -> Service:
    result = normalise_service(svc(**changes), "WAT", now)
    assert result is not None
    return result


def test_on_time(now: datetime) -> None:
    service = one(now)
    assert (service.status, service.planned, service.expected, service.in_min) == (
        "on_time",
        "18:05",
        None,
        5,
    )
    assert service.arrival and service.arrival.planned == "18:22"
    assert service.stop_count == 1
    assert service.platform == "3"
    assert service.operator == "SW"


def test_late_and_arrival(now: datetime) -> None:
    service = one(
        now,
        etd="18:12",
        subsequentCallingPoints=[
            {
                "callingPoint": [cp(et="18:29")],
            }
        ],
    )
    assert (service.status, service.delay_min, service.expected) == ("late", 7, "18:12")
    assert service.arrival and service.arrival.expected == "18:29"
    assert service.stop_count == 0


@pytest.mark.parametrize(
    ("changes", "status", "reason"),
    [
        ({"etd": "Delayed", "delayReason": "Trespassers"}, "delayed", "Trespassers"),
        (
            {"isCancelled": True, "cancelReason": "Crew <b>shortage</b>"},
            "cancelled",
            "Crew shortage",
        ),
        ({"etd": "Cancelled"}, "cancelled", ""),
        ({"filterLocationCancelled": True}, "part_cancelled", ""),
        ({"etd": "No report"}, "unknown", ""),
        ({"etd": None}, "unknown", ""),
        ({"etd": {}}, "unknown", ""),
        ({"isCancelled": "false"}, "on_time", ""),
    ],
)
def test_status(now: datetime, changes: Raw, status: str, reason: str) -> None:
    service = one(now, **changes)
    assert service.status == status
    assert service.reason == reason
    if status in ("cancelled", "part_cancelled"):
        assert service.arrival and service.arrival.cancelled


def test_destination_cancellation_reason(now: datetime) -> None:
    service = one(
        now,
        subsequentCallingPoints=[
            {
                "callingPoint": [
                    cp(isCancelled=True, cancelReason="Destination closed"),
                ]
            }
        ],
    )
    assert service.status == "part_cancelled"
    assert service.reason == "Destination closed"


@pytest.mark.parametrize("platform", [None, "", {}, [], False])
def test_missing_platform(now: datetime, platform: object) -> None:
    assert one(now, platform=platform).platform is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (5, 5),
        (12, 12),
        (0, None),
        (-1, None),
        (True, None),
        (8.5, None),
        ("8", None),
        (None, None),
        ({}, None),
        (101, None),
    ],
)
def test_lengths(value: object, expected: int | None) -> None:
    assert positive_int(value) == expected


def test_downstream_length_is_not_departure_length(now: datetime) -> None:
    service = one(now, subsequentCallingPoints=[{"callingPoint": [cp(length=8)]}])
    assert service.length is None
    assert service.stops[-1].length == 8
    assert one(now, length=10).length == 10


def test_midnight_rollover(now: datetime) -> None:
    late = now.replace(hour=23, minute=50)
    service = one(late, std="00:05", etd="00:12")
    assert (service.in_min, service.delay_min) == (15, 7)
    assert one(now.replace(hour=0, minute=10), std="23:55").in_min == -15


def test_destination_group_and_truncation(now: datetime) -> None:
    service = one(
        now,
        subsequentCallingPoints=[
            {"serviceChangeRequired": True, "callingPoint": [cp(st="19:00")]},
            {"assocIsCancelled": True, "callingPoint": [cp(st="19:01")]},
            {"callingPoint": [cp("WOK")]},
            {"callingPoint": [cp("CLJ"), cp(), cp("BYD")]},
        ],
    )
    assert [point.crs for point in service.stops] == ["CLJ", "WAT"]
    assert service.arrival and service.arrival.planned == "18:22"


@pytest.mark.parametrize("groups", [None, {}, "bad", [None, 12], [{"callingPoint": 12}]])
def test_malformed_groups(now: datetime, groups: object) -> None:
    service = one(now, subsequentCallingPoints=groups)
    assert service.stops == []
    assert service.stop_count is None
    assert service.arrival is None


def test_actual_stop_and_unknown_time(now: datetime) -> None:
    service = one(now, subsequentCallingPoints=[{"callingPoint": [cp(at="18:25")]}])
    assert service.arrival and service.arrival.state == "actual"
    assert service.arrival.expected == "18:25"
    unknown = one(now, subsequentCallingPoints=[{"callingPoint": [cp(st=None, et=None)]}])
    assert unknown.arrival and unknown.arrival.planned is None


@pytest.mark.parametrize("value", [None, "bad", "24:00", "18:60", "18:05garbage", {}, True])
def test_invalid_clock(value: object) -> None:
    assert clock(value) is None


@pytest.mark.parametrize(
    ("value", "expected"), [("8:05", "08:05"), ("18:05*", "18:05"), ("00:00", "00:00")]
)
def test_valid_clock(value: str, expected: str) -> None:
    assert clock(value) == expected


def test_time_states() -> None:
    assert time_state("18:00", "On time") == ("18:00", "on_time")
    assert time_state("18:00", "18:05", "18:03") == ("18:03", "actual")
    assert time_state("18:00", "Cancelled") == (None, "cancelled")


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        "bad",
        {"fault": "failed"},
        {"error": "secret"},
        {"errors": ["bad"]},
        {"trainServices": "bad"},
        {"busServices": {}},
    ],
)
def test_bad_boards(now: datetime, raw: object) -> None:
    with pytest.raises(ValueError):
        normalise_board(raw, "WAT", now)


def test_missing_fields_and_bad_rows(now: datetime) -> None:
    assert normalise_board({}, "WAT", now).services == []
    board = normalise_board({"trainServices": [None, 12, {}, svc(std="bad"), svc()]}, "WAT", now)
    assert len(board.services) == 1
    assert one(now, serviceID=None).id.startswith("derived-")
    assert one(now, serviceID=None).id == one(now, serviceID=None).id


def test_bus_replacement_and_ferry(now: datetime) -> None:
    board = normalise_board(
        {"trainServices": [svc(serviceType="ferry"), svc()], "busServices": [svc(serviceID="bus")]},
        "WAT",
        now,
    )
    assert {service.service_type for service in board.services} == {"train", "bus"}


def test_messages_and_generation_time(now: datetime) -> None:
    board = normalise_board(
        {
            "generatedAt": "2026-10-29T17:59:00Z",
            "nrccMessages": [
                {"Value": "<p>Delays &amp; cancellations</p>"},
                None,
                {"Value": {}},
            ],
            "areServicesAvailable": False,
        },
        "WAT",
        now,
    )
    assert board.messages == ["Delays & cancellations"]
    assert board.generated_at == datetime(2026, 10, 29, 17, 59, tzinfo=UTC)
    assert not board.services_available


@pytest.mark.parametrize("generated", [None, "bad", "2026-10-29T17:00:00", {}])
def test_missing_generation_time(now: datetime, generated: object) -> None:
    assert normalise_board({"generatedAt": generated}, "WAT", now).generated_at == now


def test_naive_now_rejected() -> None:
    with pytest.raises(ValueError):
        normalise_board({}, "WAT", datetime(2026, 10, 29))
