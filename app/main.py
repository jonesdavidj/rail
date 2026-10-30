"""HTTP boundary; all departure logic lives in independently testable modules."""

import re
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.config import ConfigLoad, Route, Settings, load_config
from app.logging import configure_logging
from app.models import BoardPage
from app.normalise import LONDON, normalise_board
from app.paging import MAX_OFFSET, MIN_OFFSET, page_board
from app.providers import DemoProvider, DepartureProvider, ProviderUnavailable, RailDataProvider

logger = configure_logging()


def london_now() -> datetime:
    return datetime.now(LONDON)


def create_app(
    settings: Settings | None = None,
    provider: DepartureProvider | None = None,
    now: Callable[[], datetime] = london_now,
) -> FastAPI:
    settings = settings or Settings.from_environment()
    loaded: ConfigLoad = load_config(settings.data_path)
    selected = provider or (DemoProvider() if settings.provider == "demo" else RailDataProvider())
    application = FastAPI(title="Rail", docs_url=None, redoc_url=None)
    logger.info(
        "config_loaded",
        extra={
            "fields": {
                "source": loaded.source,
                "warning": loaded.warning,
                "provider": selected.mode,
            }
        },
    )

    @application.middleware("http")
    async def request_log(request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.monotonic()
        allowed = {"route", "offset"} if request.url.path == "/api/board" else set()
        if request.url.path.startswith("/api/") and (
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
        # Never log raw paths, query strings or headers (untrusted data may contain secrets).
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
        return {
            "ok": True,
            "mode": selected.mode,
            "demo": selected.mode == "demo",
            "provider_ready": selected.mode == "demo",
            "config_source": loaded.source,
            "config_warning": loaded.warning,
            "degraded": loaded.warning is not None or selected.mode != "demo",
        }

    @application.get("/api/routes", response_model=list[Route])
    def routes() -> list[Route]:
        return loaded.config.routes

    @application.get("/api/board", response_model=BoardPage)
    def board(
        request: Request,
        route: Annotated[str, Query(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")],
        offset: Annotated[int, Query(ge=MIN_OFFSET, le=MAX_OFFSET)] = 0,
    ) -> BoardPage:
        if set(request.query_params) - {"route", "offset"} or any(
            len(request.query_params.getlist(key)) != 1 for key in request.query_params
        ):
            raise HTTPException(422, "Unknown or repeated query parameter")
        config = next((item for item in loaded.config.routes if item.id == route), None)
        if config is None:
            raise HTTPException(404, "Unknown route")
        moment = now()
        try:
            raw = selected.board(config, offset, moment)
            normalised = normalise_board(raw, config.destination, moment)
            return page_board(normalised, config, offset, selected)
        except ProviderUnavailable as error:
            raise HTTPException(503, str(error)) from None
        except ValueError:
            logger.warning("invalid_provider_board")
            raise HTTPException(502, "Provider returned an invalid board") from None

    @application.get("/", response_class=FileResponse)
    def index() -> FileResponse:
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    return application


app = create_app()
