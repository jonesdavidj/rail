"""Strict route configuration, loaded only from the runtime data directory."""

import json
import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

STATIONS: dict[str, str] = json.loads(
    (Path(__file__).parent / "data" / "stations.json").read_text(encoding="utf-8")
)
CRS = Annotated[str, Field(pattern=r"^[A-Z]{3}$", strict=True)]
RouteID = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$", strict=True)]


class Route(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: RouteID
    label: str = Field(min_length=1, max_length=100)
    origin: CRS
    destination: CRS
    min_departure_minutes: int = Field(default=0, ge=0, le=120)
    page_size: int = Field(default=7, ge=1, le=25)

    @field_validator("origin", "destination")
    @classmethod
    def known_station(cls, value: str) -> str:
        if value not in STATIONS:
            raise ValueError("CRS is not in the bundled station catalogue")
        return value

    @field_validator("label")
    @classmethod
    def clean_label(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("label must contain visible text and no control characters")
        return value.strip()

    @model_validator(mode="after")
    def distinct_stations(self) -> "Route":
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")
        return self


class RouteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    version: Literal[1] = 1
    routes: list[Route] = Field(max_length=32)

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("version must be an integer")
        return value

    @model_validator(mode="after")
    def unique_ids(self) -> "RouteConfig":
        if len({route.id for route in self.routes}) != len(self.routes):
            raise ValueError("route IDs must be unique")
        return self


def defaults() -> RouteConfig:
    return RouteConfig(routes=[
        Route(id="out", label="Surbiton to London Waterloo", origin="SUR", destination="WAT"),
        Route(id="back", label="London Waterloo to Surbiton", origin="WAT", destination="SUR"),
    ])


class ConfigLoad(BaseModel):
    config: RouteConfig
    source: Literal["file", "defaults"]
    warning: str | None = None


def load_config(data_path: Path) -> ConfigLoad:
    """Never write or replace a missing/broken config during startup."""
    try:
        path = data_path / "routes.json"
        if path.stat().st_size > 256_000:
            return ConfigLoad(config=defaults(), source="defaults", warning="config_too_large")
        config = RouteConfig.model_validate_json(path.read_bytes())
        return ConfigLoad(config=config, source="file")
    except FileNotFoundError:
        warning = "config_missing"
    except (ValidationError, UnicodeError):
        warning = "config_invalid"
    except OSError:
        warning = "config_unreadable"
    return ConfigLoad(config=defaults(), source="defaults", warning=warning)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_path: Path = Path("/data")
    provider: Literal["demo", "rail_data"] = "demo"

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            data_path=Path(os.environ.get("RAIL_DATA_PATH", "/data")),
            provider=os.environ.get("RAIL_PROVIDER", "demo"),
        )
