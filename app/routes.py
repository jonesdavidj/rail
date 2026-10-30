"""One-process route store; commit the complete validated document atomically."""

import os
import tempfile
from pathlib import Path
from threading import RLock

from app.config import STATIONS, ConfigLoad, Route, RouteConfig, RouteWrite, load_config


class RouteConflict(ValueError):
    pass


class RouteStore:
    def __init__(self, data_path: Path) -> None:
        self.path = data_path / "routes.json"
        self.lock = RLock()
        self.loaded = load_config(data_path)

    def snapshot(self) -> ConfigLoad:
        with self.lock:
            return self.loaded.model_copy(deep=True)

    def write(self, change: RouteWrite | str, operation: str) -> list[Route]:
        with self.lock:
            routes = list(self.loaded.config.routes)
            identity = change if isinstance(change, str) else change.id
            index = next((i for i, route in enumerate(routes) if route.id == identity), None)
            if operation == "create" and index is not None:
                raise RouteConflict("Route ID already exists")
            if operation != "create" and index is None:
                raise KeyError(identity)
            if isinstance(change, str):
                routes = [route for route in routes if route.id != identity]
            else:
                route = Route.model_validate(change.model_dump(exclude={"add_return_journey"}))
                if index is None:
                    routes.append(route)
                else:
                    routes[index] = route
                if change.add_return_journey:
                    if any(
                        r.origin == route.destination and r.destination == route.origin
                        for r in routes
                    ):
                        raise RouteConflict("Return journey is already saved")
                    reverse_id = route.id[:48] + "-return"
                    if any(existing.id == reverse_id for existing in routes):
                        raise RouteConflict("Generated return route ID already exists")
                    routes.append(
                        Route(
                            id=reverse_id,
                            label=f"{STATIONS[route.destination]} to {STATIONS[route.origin]}"[
                                :100
                            ],
                            origin=route.destination,
                            destination=route.origin,
                            min_departure_minutes=route.min_departure_minutes,
                            page_size=route.page_size,
                            fast_max_stops=route.fast_max_stops,
                        )
                    )
            config = RouteConfig(routes=routes)
            return self.save(config)

    def reorder(self, ids: list[str]) -> list[Route]:
        with self.lock:
            current = {route.id: route for route in self.loaded.config.routes}
            if len(ids) != len(current) or set(ids) != set(current):
                raise RouteConflict("Routes have changed; reload settings and try again")
            return self.save(RouteConfig(routes=[current[identity] for identity in ids]))

    def save(self, config: RouteConfig) -> list[Route]:
        """Called under the store lock, after validating the entire resulting list."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".routes-",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(config.model_dump_json(indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.loaded = ConfigLoad(config=config, source="file")
        return list(config.routes)
