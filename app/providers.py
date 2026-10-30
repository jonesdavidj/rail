"""Departure providers. Only the deterministic demo provider performs work in phase 1."""

from datetime import datetime, timedelta
from typing import Literal, Protocol

from app.config import STATIONS, Route
from app.normalise import LONDON, Raw
from app.rail_data import ProviderBoard


class DepartureProvider(Protocol):
    mode: Literal["demo", "rail_data"]
    ready: bool

    def board(self, route: Route, offset: int, now: datetime) -> ProviderBoard: ...


class DemoProvider:
    mode: Literal["demo", "rail_data"] = "demo"

    ready = True

    def board(self, route: Route, offset: int, now: datetime) -> ProviderBoard:
        """Stable clock-anchored services, so refresh/paging don't regenerate identities.

        All routes are synthetic, including their timings and stopping patterns.
        Buses are explicit replacement services, not silently presented as trains.
        """
        local = now.astimezone(LONDON)
        anchor = local.replace(second=0, microsecond=0) - timedelta(minutes=local.minute % 10)
        services: list[Raw] = []
        for index in range(-6, 27):
            departure = anchor + timedelta(minutes=index * 10 + 5)
            delta = (departure.timestamp() - now.timestamp()) / 60
            if not offset <= delta <= offset + 120:
                continue
            scenario = index % 8
            estimate = (departure + timedelta(minutes=7)).strftime("%H:%M")
            cancelled = scenario == 3
            bus = scenario == 7
            arrival = departure + timedelta(minutes=45 if bus else 24)
            stops: list[Raw] = []
            if {route.origin, route.destination} == {"SUR", "WAT"}:
                stops.append(
                    {
                        "locationName": "Clapham Junction",
                        "crs": "CLJ",
                        "st": (departure + timedelta(minutes=14)).strftime("%H:%M"),
                        "et": "On time",
                    }
                )
            stops.append(
                {
                    "locationName": STATIONS[route.destination],
                    "crs": route.destination,
                    "st": arrival.strftime("%H:%M"),
                    "et": "Cancelled"
                    if cancelled
                    else (
                        (arrival + timedelta(minutes=7)).strftime("%H:%M")
                        if scenario == 1
                        else "Delayed"
                        if scenario == 2
                        else "On time"
                    ),
                    "isCancelled": cancelled,
                }
            )
            services.append(
                {
                    "serviceID": f"demo-{route.id}-{departure.isoformat()}",
                    "std": departure.strftime("%H:%M"),
                    "etd": "Cancelled"
                    if cancelled
                    else estimate
                    if scenario == 1
                    else ("Delayed" if scenario == 2 else "On time"),
                    "platform": None if scenario in (4, 7) else str(index % 4 + 1),
                    "operator": "Demo Rail",
                    "operatorCode": "DE",
                    "isCancelled": cancelled,
                    "serviceType": "bus" if bus else "train",
                    "length": None if scenario in (4, 7) else [5, 8, 10, 12][index % 4],
                    "cancelReason": "Demo: shortage of train crew" if cancelled else "",
                    "delayReason": "Demo: signalling fault" if scenario in (1, 2) else "",
                    "origin": [{"locationName": STATIONS[route.origin], "crs": route.origin}],
                    "destination": [
                        {"locationName": STATIONS[route.destination], "crs": route.destination}
                    ],
                    "subsequentCallingPoints": [{"callingPoint": stops}],
                }
            )
        return ProviderBoard(
            {
                "generatedAt": now.isoformat(),
                "trainServices": services,
                "areServicesAvailable": True,
                "nrccMessages": [{"Value": "Demo data. These are not real trains."}],
            }
        )
