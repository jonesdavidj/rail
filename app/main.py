"""HTTP boundary; provider, config and parsing logic stay independent of HTTP."""

import hmac
import re
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.config import Route, RouteID, RouteOrder, RouteWrite, Settings
from app.integrations.home_assistant import summary_router
from app.logging import configure_logging
from app.models import BoardPage
from app.normalise import LONDON, normalise_board
from app.paging import MAX_OFFSET, MIN_OFFSET, cursor_offset, page_board, read_cursor
from app.providers import DemoProvider, DepartureProvider
from app.rail_data import ProviderError, RailDataProvider
from app.routes import RouteConflict, RouteStore
from app.stations import search_stations

logger = configure_logging()


def london_now() -> datetime:
    return datetime.now(LONDON)


def create_app(
    settings: Settings | None = None,
    provider: DepartureProvider | None = None,
    now: Callable[[], datetime] = london_now,
) -> FastAPI:
    settings = settings or Settings.from_environment()
    store = RouteStore(settings.data_path)
    live = settings.provider == "rail_data" or (
        settings.provider == "auto"
        and (settings.api_key.get_secret_value() or settings.api_key_file)
    )
    selected = provider or (RailDataProvider(settings) if live else DemoProvider())
    application = FastAPI(title="Rail", docs_url=None, redoc_url=None)
    logger.info(
        "config_loaded",
        extra={
            "fields": {
                "source": store.loaded.source,
                "warning": store.loaded.warning,
                "provider": selected.mode,
            }
        },
    )

    @application.middleware("http")
    async def request_log(request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.monotonic()
        path = request.url.path
        allowed = (
            {"route", "offset", "cursor", "fast"}
            if path == "/api/board"
            else (
                {"route"}
                if path == "/api/summary"
                else (
                    {"q"}
                    if path == "/api/stations"
                    else ({"id"} if path == "/api/routes" and request.method == "DELETE" else set())
                )
            )
        )
        write = path in ("/api/routes", "/api/routes/order") and request.method in (
            "POST",
            "PUT",
            "DELETE",
        )
        expected = settings.admin_token.get_secret_value()
        supplied = request.headers.get("Authorization", "")
        if (
            write
            and expected
            and not hmac.compare_digest(supplied.encode(), ("Bearer " + expected).encode())
        ):
            response = JSONResponse(
                {"detail": "Admin token required"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        elif path.startswith("/api/") and (
            set(request.query_params) - allowed
            or any(len(request.query_params.getlist(key)) != 1 for key in request.query_params)
            or (
                "offset" in request.query_params
                and re.fullmatch(r"-?[0-9]+", request.query_params["offset"]) is None
            )
        ):
            response = JSONResponse({"detail": "Invalid query parameters"}, status_code=422)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        logger.info(
            "http_request",
            extra={
                "fields": {
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                }
            },
        )
        return response

    @application.get("/api/health")
    def health() -> dict[str, object]:
        loaded = store.snapshot()
        return {
            "ok": True,
            "mode": selected.mode,
            "demo": selected.mode == "demo",
            "provider_ready": selected.ready,
            "write_token_required": bool(settings.admin_token.get_secret_value()),
            "config_source": loaded.source,
            "config_warning": loaded.warning,
            "refresh_seconds": settings.refresh_seconds,
            "degraded": loaded.warning is not None or not selected.ready,
        }

    @application.get("/api/routes", response_model=list[Route])
    def routes() -> list[Route]:
        return store.snapshot().config.routes

    def change_route(change: RouteWrite | str, operation: str) -> list[Route]:
        try:
            return store.write(change, operation)
        except RouteConflict as error:
            raise HTTPException(409, str(error)) from None
        except KeyError:
            raise HTTPException(404, "Unknown route") from None
        except ValidationError:
            raise HTTPException(
                422, "Route list would violate config limits or unique IDs"
            ) from None
        except OSError:
            logger.error("route_save_failed")
            raise HTTPException(
                503, "Could not save routes; previous configuration retained"
            ) from None

    @application.post("/api/routes", response_model=list[Route], status_code=201)
    def add_route(route: RouteWrite) -> list[Route]:
        return change_route(route, "create")

    @application.put("/api/routes", response_model=list[Route])
    def update_route(route: RouteWrite) -> list[Route]:
        return change_route(route, "update")

    @application.delete("/api/routes", response_model=list[Route])
    def delete_route(id: Annotated[RouteID, Query()]) -> list[Route]:
        return change_route(id, "delete")

    @application.put("/api/routes/order", response_model=list[Route])
    def reorder_routes(order: RouteOrder) -> list[Route]:
        try:
            return store.reorder(order.ids)
        except RouteConflict as error:
            raise HTTPException(409, str(error)) from None
        except OSError:
            raise HTTPException(503, "Could not save route order; please try again") from None

    @application.get("/api/stations")
    def stations(q: Annotated[str, Query(min_length=1, max_length=100)]) -> list[dict[str, str]]:
        return search_stations(q)

    @application.get("/api/board", response_model=BoardPage, response_model_exclude_none=True)
    def board(
        route: Annotated[RouteID, Query()],
        offset: Annotated[int, Query(ge=MIN_OFFSET, le=MAX_OFFSET)] = 0,
        cursor: Annotated[str | None, Query(min_length=1, max_length=4096)] = None,
        fast: Annotated[str, Query(pattern=r"^[01]$")] = "0",
    ) -> BoardPage | JSONResponse:
        config = next((r for r in store.snapshot().config.routes if r.id == route), None)
        if config is None:
            raise HTTPException(404, "Unknown route")
        moment = now()
        try:
            boundary = read_cursor(cursor, config, moment) if cursor else None
            if boundary:
                offset = cursor_offset(boundary, moment)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        try:
            result = selected.board(config, offset, moment)
            page = page_board(
                normalise_board(result.raw, config.destination, moment),
                config,
                offset,
                selected,
                moment,
                boundary,
                fast == "1",
            )
            return page.model_copy(
                update={
                    "stale": result.stale,
                    "error": result.error,
                    "error_code": result.error_code,
                    "cache_age_seconds": result.cache_age_seconds,
                }
            )
        except ProviderError as error:
            logger.warning("provider_error", extra={"fields": {"code": error.code}})
            return JSONResponse(
                {"error": str(error), "error_code": error.code, "stale": False},
                status_code=error.status,
                headers={"Retry-After": str(error.retry_after)},
            )
        except ValueError:
            logger.warning("invalid_provider_board")
            raise HTTPException(502, "Provider returned an invalid board") from None

    application.include_router(summary_router(store, selected, now))

    @application.get("/", response_class=FileResponse)
    def index() -> FileResponse:
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @application.get("/manifest.webmanifest", include_in_schema=False)
    def manifest() -> FileResponse:
        return FileResponse(
            Path(__file__).parent / "static" / "manifest.webmanifest",
            media_type="application/manifest+json",
        )

    application.mount(
        "/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static"
    )

    return application


app = create_app()
