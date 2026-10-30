"""Application-owned response types, independent of Darwin payloads."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TimeState = Literal["on_time", "estimated", "actual", "cancelled", "unknown"]
Status = Literal["on_time", "late", "delayed", "cancelled", "part_cancelled", "unknown"]


class Stop(BaseModel):
    name: str
    crs: str
    planned: str | None = None
    expected: str | None = None
    state: TimeState = "unknown"
    cancelled: bool = False
    length: int | None = None


class Arrival(BaseModel):
    planned: str | None = None
    expected: str | None = None
    state: TimeState = "unknown"
    cancelled: bool = False


class Service(BaseModel):
    id: str
    planned: str
    expected: str | None = None
    in_min: int
    status: Status
    delay_min: int | None = None
    platform: str = "TBC"
    operator: str = ""
    operator_name: str = ""
    origin: str = ""
    destination: str = ""
    length: int | None = None
    reason: str = ""
    arrival: Arrival | None = None
    stops: list[Stop] = Field(default_factory=list)
    stop_count: int | None = None
    service_type: Literal["train", "bus"] = "train"
    future_delay: bool = False
    future_cancellation: bool = False
    is_fast: bool = False
    journey_minutes: int | None = None
    is_quickest: bool = False


class NormalisedBoard(BaseModel):
    generated_at: datetime
    services: list[Service]
    messages: list[str]
    services_available: bool = True


class BoardPage(NormalisedBoard):
    route: str
    title: str
    mode: Literal["demo", "rail_data"]
    demo: bool
    offset: int
    next_offset: int | None = None
    next_cursor: str | None = None
    earlier_offset: int | None = None
    has_next: bool = False
    stale: bool = False
    error: str | None = None
    error_code: str | None = None
    cache_age_seconds: int = 0
    fast_only: bool = False
    fast_count: int = 0
    total_count: int = 0
