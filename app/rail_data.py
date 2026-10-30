"""RDM REST transport and a bounded, coalescing in-memory board cache."""

import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import Lock
from typing import Literal

from app.config import Route, Settings
from app.normalise import Raw, normalise_board

MAX_RESPONSE_BYTES = 2_000_000
STALE_SECONDS = 900


class ProviderError(Exception):
    def __init__(self, code: str, message: str, status: int = 502, retry_after: int = 30) -> None:
        super().__init__(message)
        self.code, self.status, self.retry_after = code, status, retry_after


def http_error(status: int, retry_after: str | None = None) -> ProviderError:
    if status in (401, 403):
        return ProviderError("authentication", "Rail Data rejected the API key or subscription.")
    if status == 429:
        wait = 60
        if retry_after:
            try:
                wait = (
                    int(retry_after)
                    if retry_after.isdecimal()
                    else int(
                        (parsedate_to_datetime(retry_after) - datetime.now(UTC)).total_seconds()
                    )
                )
            except (ValueError, TypeError, OverflowError):
                pass
        return ProviderError(
            "rate_limit",
            "Rail Data rate limit reached; please try later.",
            503,
            max(wait, 30),
        )
    if 300 <= status < 400:
        return ProviderError("redirect", "Rail Data returned a redirect; check the configured URL.")
    if status in (400, 404, 500):
        return ProviderError(
            "routing",
            "Rail Data could not serve this route. Check the product "
            "Specification URL and station codes; the provider may be unavailable.",
        )
    return ProviderError("upstream", "Rail Data is temporarily unavailable.", 503)


def transport_error(error: Exception) -> ProviderError:
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, TimeoutError):
        return ProviderError("timeout", "Rail Data timed out (15-second network timeout).", 504)
    if isinstance(error, http.client.HTTPException):
        return ProviderError("bad_json", "Rail Data returned an incomplete HTTP response.")
    return ProviderError("connection", "Could not reach Rail Data; please try later.", 503)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        return None


@dataclass(frozen=True)
class ProviderBoard:
    raw: Raw
    stale: bool = False
    error: str | None = None
    error_code: str | None = None
    cache_age_seconds: int = 0


@dataclass
class CacheEntry:
    result: ProviderBoard | None = None
    fetched: float = 0
    retry_at: float = 0
    error: ProviderError | None = None


def parse_board(body: bytes, destination: str, now: datetime) -> Raw:
    if len(body) > MAX_RESPONSE_BYTES:
        raise ProviderError("response_size", "Rail Data response exceeded the size limit.")
    try:
        raw = json.loads(body)
        if not isinstance(raw, dict) or not any(
            key in raw for key in ("trainServices", "busServices", "areServicesAvailable")
        ):
            raise ValueError("not a board")
        normalise_board(raw, destination, now)
    except (ValueError, UnicodeError, RecursionError):
        raise ProviderError(
            "bad_json", "Rail Data returned invalid JSON or an invalid board."
        ) from None
    return raw


class RailDataProvider:
    mode: Literal["demo", "rail_data"] = "rail_data"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.lock = Lock()
        self.cache: OrderedDict[tuple[str, str, int], CacheEntry] = OrderedDict()
        self.pending: dict[tuple[str, str, int], Future[ProviderBoard]] = {}
        self.opener = urllib.request.build_opener(NoRedirect())
        self.configuration_error: str | None = None
        self.key = ""
        self.base = ""
        try:
            key = settings.api_key.get_secret_value()
            if key and settings.api_key_file:
                raise ValueError(
                    "Set either RAIL_DATA_API_KEY or RAIL_DATA_API_KEY_FILE, not both."
                )
            if settings.api_key_file:
                with settings.api_key_file.open(encoding="utf-8") as handle:
                    contents = handle.read(4097)
                    if len(contents) > 4096:
                        raise ValueError("Rail Data API key file exceeds the size limit.")
                    key = contents.strip()
            if not key or len(key) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key):
                raise ValueError(
                    "Rail Data API key is missing or invalid; check its environment/file."
                )
            if any(character.isspace() or character == "\\" for character in settings.base_url):
                raise ValueError("Rail Data base URL must not contain whitespace or backslashes.")
            url = urllib.parse.urlsplit(settings.base_url)
            if (
                url.scheme != "https"
                or url.hostname not in settings.allowed_hosts
                or url.username
                or url.password
                or url.netloc.lower() != url.hostname
                or url.query
                or url.fragment
                or not url.path
                or not settings.base_url.isascii()
                or not settings.allowed_hosts
            ):
                raise ValueError(
                    "Rail Data base URL must use HTTPS on an explicitly allowed host, "
                    "without credentials, port, query or fragment."
                )
            self.key, self.base = key, settings.base_url.rstrip("/")
        except OSError:
            self.configuration_error = "Cannot read the Rail Data API key file."
        except ValueError as error:
            self.configuration_error = str(error)
        self.ready = self.configuration_error is None

    def fetch(self, route: Route, offset: int, now: datetime) -> Raw:
        if not self.ready:
            raise ProviderError(
                "configuration", self.configuration_error or "Provider not ready", 503
            )
        if not -60 <= offset <= 119:
            raise ProviderError("offset", "Requested time offset is outside the app's range.", 422)
        query = urllib.parse.urlencode(
            {
                "filterCrs": route.destination,
                "filterType": "to",
                "timeOffset": offset,
                "timeWindow": 120,
                "numRows": 50,
            }
        )
        request = urllib.request.Request(
            f"{self.base}/GetDepBoardWithDetails/{route.origin}?{query}",
            headers={
                "x-apikey": self.key,
                "Accept": "application/json",
                "User-Agent": "RailHomeBoard/2",
            },
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            mapped = http_error(error.code, error.headers.get("Retry-After"))
            error.close()
            raise mapped from None
        except (OSError, urllib.error.URLError, http.client.HTTPException) as error:
            raise transport_error(error) from None
        return parse_board(body, route.destination, now)

    def board(self, route: Route, offset: int, now: datetime) -> ProviderBoard:
        key = route.origin, route.destination, offset
        with self.lock:
            entry = self.cache.setdefault(key, CacheEntry())
            self.cache.move_to_end(key)
            moment = time.monotonic()
            if entry.result and moment - entry.fetched < self.settings.cache_ttl:
                return self.available(entry, moment)
            if moment < entry.retry_at and entry.error:
                return self.available(entry, moment)
            future = self.pending.get(key)
            leader = future is None
            if future is None:
                future = Future()
                self.pending[key] = future
        if not leader:
            return future.result()
        try:
            try:
                raw = self.fetch(route, offset, now)
                with self.lock:
                    entry.result = ProviderBoard(raw)
                    entry.fetched, entry.error, entry.retry_at = time.monotonic(), None, 0
            except ProviderError as error:
                with self.lock:
                    entry.error = error
                    entry.retry_at = time.monotonic() + max(
                        self.settings.cache_ttl, error.retry_after
                    )
            with self.lock:
                result = self.available(entry, time.monotonic())
            future.set_result(result)
            return result
        except Exception as error:
            future.set_exception(error)
            raise
        finally:
            with self.lock:
                del self.pending[key]
                while len(self.cache) > 256:
                    victim = next((item for item in self.cache if item not in self.pending), None)
                    if victim is None:
                        break
                    del self.cache[victim]

    def available(self, entry: CacheEntry, moment: float) -> ProviderBoard:
        age = max(0, int(moment - entry.fetched))
        if entry.result and (entry.error is None or moment - entry.fetched <= STALE_SECONDS):
            return ProviderBoard(
                entry.result.raw,
                stale=entry.error is not None,
                error=str(entry.error) if entry.error else None,
                error_code=entry.error.code if entry.error else None,
                cache_age_seconds=age,
            )
        raise entry.error or ProviderError("unavailable", "No departure board is available.", 503)
