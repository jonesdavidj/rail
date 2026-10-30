"""Defensive adapter for the public Darwin JSON shape inspected in ldbws.json.

No network I/O. Unknown values remain unknown; malformed services are skipped.
Current RDM runtime limits and populated fields still need a key-assisted live check.
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
    for group in objects(raw.get("subsequentCallingPoints")):
        if group.get("serviceChangeRequired") is True or group.get("assocIsCancelled") is True:
            continue
        if group.get("serviceType") not in (None, "train", "bus"):
            continue
        points = objects(group.get("callingPoint"))
        for index, point in enumerate(points):
            if point.get("crs") == destination:
                return points[: index + 1]
    return []


def location_name(value: object) -> str:
    return ", ".join(filter(None, (text(item.get("locationName")) for item in objects(value))))


def normalise_service(raw: Raw, destination: str, now: datetime) -> Service | None:
    planned = clock(raw.get("std"))
    kind = raw.get("serviceType", "train")
    if planned is None or kind not in ("train", "bus"):
        return None
    expected, state = time_state(planned, raw.get("etd"))
    cancelled = raw.get("isCancelled") is True or state == "cancelled"
    points = calling_points(raw, destination)
    stops: list[Stop] = []
    for point in points:
        scheduled = clock(point.get("st"))
        estimate, point_state = time_state(scheduled, point.get("et"), point.get("at"))
        stops.append(
            Stop(
                name=text(point.get("locationName")) or text(point.get("crs")),
                crs=text(point.get("crs")),
                planned=scheduled,
                expected=estimate if estimate != scheduled else None,
                state=point_state,
                cancelled=point.get("isCancelled") is True or point_state == "cancelled",
                length=positive_int(point.get("length")),
            )
        )
    partial = not cancelled and (
        raw.get("filterLocationCancelled") is True or bool(stops and stops[-1].cancelled)
    )
    delay = minutes_between(planned, expected) if expected else None
    status: Status = "unknown"
    if cancelled:
        status = "cancelled"
    elif partial:
        status = "part_cancelled"
    elif text(raw.get("etd")).lower() == "delayed":
        status = "delayed"
    elif state != "unknown":
        status = "late" if delay is not None and delay > 0 else "on_time"
    reason = text(raw.get("cancelReason")) if cancelled or partial else ""
    if not reason and partial and points:
        reason = text(points[-1].get("cancelReason"))
    reason = reason or text(raw.get("delayReason"))
    arrival = None
    if stops:
        final = stops[-1]
        arrival = Arrival(
            planned=final.planned,
            expected=final.expected,
            state=final.state,
            cancelled=final.cancelled or cancelled or partial,
        )
    platform = raw.get("platform")
    platform_text = (
        text(platform)
        if isinstance(platform, str)
        else (str(platform) if type(platform) is int else "")
    )
    identity = text(raw.get("serviceID"))
    if not identity:
        seed = repr((planned, raw.get("origin"), raw.get("destination"), points))
        identity = "derived-" + hashlib.sha256(seed.encode()).hexdigest()[:20]
    return Service(
        id=identity,
        planned=planned,
        expected=expected if expected != planned else None,
        in_min=math.floor((departure_datetime(planned, now).timestamp() - now.timestamp()) / 60),
        status=status,
        delay_min=delay,
        platform=platform_text or None,
        operator=text(raw.get("operatorCode")) or text(raw.get("operator")),
        operator_name=text(raw.get("operator")),
        origin=location_name(raw.get("origin")),
        destination=location_name(raw.get("destination")),
        length=positive_int(raw.get("length")),
        reason=reason,
        arrival=arrival,
        stops=stops,
        stop_count=max(len(stops) - 1, 0) if stops else None,
        service_type=kind,
    )


def normalise_board(raw: object, destination: str, now: datetime) -> NormalisedBoard:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not isinstance(raw, dict):
        raise ValueError("board must be an object")
    if any(raw.get(key) for key in ("error", "errors", "fault")):
        raise ValueError("upstream returned an error")
    services: list[Service] = []
    for collection in ("trainServices", "busServices"):
        entries = raw.get(collection)
        if entries is not None and not isinstance(entries, list):
            raise ValueError("service collection must be a list")
        for item in objects(entries):
            candidate = dict(item)
            if collection == "busServices":
                candidate["serviceType"] = "bus"
            if service := normalise_service(candidate, destination, now):
                services.append(service)
    services.sort(key=lambda service: (service.in_min, service.id))
    messages = [text(message.get("Value")) for message in objects(raw.get("nrccMessages"))]
    generated = now
    if isinstance(raw.get("generatedAt"), str):
        try:
            parsed = datetime.fromisoformat(raw["generatedAt"].replace("Z", "+00:00"))
            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                generated = parsed
        except ValueError:
            pass
    return NormalisedBoard(
        generated_at=generated,
        services=services,
        messages=[message for message in messages if message][:3],
        services_available=raw.get("areServicesAvailable") is not False,
    )
