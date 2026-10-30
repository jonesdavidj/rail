"""Defensive adapter for the public Darwin JSON shape inspected in ldbws.json.

No network I/O. Unknown values remain unknown; malformed services are skipped.
Verified feed facts in AGENTS.md take precedence over schema guesses.
"""

import hashlib
import html
import math
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.models import Arrival, NormalisedBoard, Service, Status, Stop, TimeState

LONDON = ZoneInfo("Europe/London")
Raw = dict[str, Any]


def field(raw: Raw, name: str, default: object = None) -> object:
    """Darwin field casing varies at every level; preserve original raw responses."""
    if name in raw:
        return raw[name]
    for key, value in raw.items():
        if key.casefold() == name.casefold():
            return value
    return default


def objects(value: object) -> list[Raw]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", value)).split())


def clock(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(\d{1,2}):(\d{2})\*?", value.strip())
    if not match:
        return None
    hour, minute = map(int, match.groups())
    return f"{hour:02d}:{minute:02d}" if hour < 24 and minute < 60 else None


def positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 < value <= 100 else None
    return None


def time_state(
    planned: object, estimate: object, actual: object = None
) -> tuple[str | None, TimeState]:
    if actual_time := clock(actual):
        return actual_time, "actual"
    if expected := clock(estimate):
        return expected, "estimated"
    status = text(estimate).lower()
    if status == "on time":
        return clock(planned), "on_time"
    if status == "cancelled":
        return None, "cancelled"
    return None, "unknown"


def minutes_between(start: str, end: str) -> int:
    first = int(start[:2]) * 60 + int(start[3:])
    last = int(end[:2]) * 60 + int(end[3:])
    return (last - first + 720) % 1440 - 720


def departure_datetime(value: str, reference: datetime) -> datetime:
    """Place a public HH:MM in the bounded board window, including midnight."""
    local = reference.astimezone(LONDON)
    result = local.replace(hour=int(value[:2]), minute=int(value[3:]), second=0, microsecond=0)
    if result - local < -timedelta(hours=6):
        result += timedelta(days=1)
    elif result - local > timedelta(hours=18):
        result -= timedelta(days=1)
    return result


def calling_points(raw: Raw, destination: str) -> list[Raw]:
    for group in objects(field(raw, "subsequentCallingPoints")):
        if (
            field(group, "serviceChangeRequired") is True
            or field(group, "assocIsCancelled") is True
        ):
            continue
        if field(group, "serviceType") not in (None, "train", "bus"):
            continue
        points = objects(field(group, "callingPoint"))
        for index, point in enumerate(points):
            if field(point, "crs") == destination:
                return points[: index + 1]
    return []


def location_name(value: object) -> str:
    return ", ".join(filter(None, (text(field(item, "locationName")) for item in objects(value))))


def normalise_service(raw: Raw, destination: str, now: datetime) -> Service | None:
    planned = clock(field(raw, "std"))
    kind = field(raw, "serviceType", "train")
    if planned is None or kind not in ("train", "bus"):
        return None
    expected, state = time_state(planned, field(raw, "etd"))
    cancelled = field(raw, "isCancelled") is True or state == "cancelled"
    points = calling_points(raw, destination)
    stops: list[Stop] = []
    for point in points:
        scheduled = clock(field(point, "st"))
        estimate, point_state = time_state(scheduled, field(point, "et"), field(point, "at"))
        stops.append(
            Stop(
                name=text(field(point, "locationName")) or text(field(point, "crs")),
                crs=text(field(point, "crs")),
                planned=scheduled,
                expected=estimate if estimate != scheduled else None,
                state=point_state,
                cancelled=field(point, "isCancelled") is True or point_state == "cancelled",
                length=positive_int(field(point, "length")),
            )
        )
    partial = not cancelled and (
        field(raw, "filterLocationCancelled") is True or bool(stops and stops[-1].cancelled)
    )
    delay = minutes_between(planned, expected) if expected else None
    status: Status = "unknown"
    if cancelled:
        status = "cancelled"
    elif partial:
        status = "part_cancelled"
    elif text(field(raw, "etd")).lower() == "delayed":
        status = "delayed"
    elif state != "unknown":
        status = "late" if delay is not None and delay > 0 else "on_time"
    reason = text(field(raw, "cancelReason")) if cancelled or partial else ""
    if not reason and partial and points:
        reason = text(field(points[-1], "cancelReason"))
    reason = reason or text(field(raw, "delayReason"))
    arrival = None
    if stops:
        final = stops[-1]
        arrival = Arrival(
            planned=final.planned,
            expected=final.expected,
            state=final.state,
            cancelled=final.cancelled or cancelled or partial,
        )
    platform = field(raw, "platform")
    platform_text = (
        text(platform)
        if isinstance(platform, str)
        else (str(platform) if type(platform) is int else "")
    )
    identity = text(field(raw, "serviceID"))
    if not identity:
        seed = repr((planned, field(raw, "origin"), field(raw, "destination"), points))
        identity = "derived-" + hashlib.sha256(seed.encode()).hexdigest()[:20]
    return Service(
        id=identity,
        planned=planned,
        expected=expected if expected != planned else None,
        in_min=math.floor((departure_datetime(planned, now).timestamp() - now.timestamp()) / 60),
        status=status,
        delay_min=delay,
        platform=platform_text or "TBC",
        operator=text(field(raw, "operatorCode")) or text(field(raw, "operator")),
        operator_name=text(field(raw, "operator")),
        origin=location_name(field(raw, "origin")),
        destination=location_name(field(raw, "destination")),
        length=positive_int(field(raw, "length")),
        reason=reason,
        arrival=arrival,
        stops=stops,
        stop_count=max(len(stops) - 1, 0) if stops else None,
        service_type=kind,
        future_delay=field(raw, "futureDelay") is True,
        future_cancellation=field(raw, "futureCancellation") is True,
    )


def normalise_board(raw: object, destination: str, now: datetime) -> NormalisedBoard:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not isinstance(raw, dict):
        raise ValueError("board must be an object")
    if any(field(raw, key) for key in ("error", "errors", "fault")):
        raise ValueError("upstream returned an error")
    services: list[Service] = []
    for collection in ("trainServices", "busServices"):
        entries = field(raw, collection)
        if entries is not None and not isinstance(entries, list):
            raise ValueError("service collection must be a list")
        for item in objects(entries):
            candidate = dict(item)
            if collection == "busServices":
                candidate["serviceType"] = "bus"
            if service := normalise_service(candidate, destination, now):
                services.append(service)
    services.sort(key=lambda service: (service.in_min, service.id))
    messages = [text(field(message, "Value")) for message in objects(field(raw, "nrccMessages"))]
    generated = now
    stamp = field(raw, "generatedAt")
    if isinstance(stamp, str):
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                generated = parsed
        except ValueError:
            pass
    return NormalisedBoard(
        generated_at=generated,
        services=services,
        messages=[message for message in messages if message],
        services_available=field(raw, "areServicesAvailable") is not False,
    )
