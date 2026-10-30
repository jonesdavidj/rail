#!/usr/bin/env python3
"""Train times board: Surbiton <-> London Waterloo.

Small standard-library web service. It calls the Rail Data Marketplace
Live Departure Board (Darwin) from the server, so the API key never reaches the
browser, and serves a single-page two-tab dashboard.

Environment:
  RAIL_DATA_API_KEY   consumer key for the "Live Departure Board" product
  RAIL_DATA_BASE_URL  product base URL (check the product's Specification tab)
  PORT                listen port (default 8099)
  MOCK                1 forces demo data; demo data is also used when no key is set
  CACHE_TTL           seconds to cache each upstream request (default 30)
"""
import html
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
HERE = Path(__file__).resolve().parent

DEFAULT_BASE = "https://api1.raildata.org.uk/1010-live-departure-board-dep1_2/LDBWS/api/20220120"
ALLOWED_HOST = os.environ.get("RAIL_DATA_ALLOWED_HOST", "api1.raildata.org.uk")

ROUTES = {
    "out": {"from": "SUR", "to": "WAT", "from_name": "Surbiton", "to_name": "London Waterloo",
            "title": "Surbiton to London Waterloo"},
    "back": {"from": "WAT", "to": "SUR", "from_name": "London Waterloo", "to_name": "Surbiton",
             "title": "London Waterloo to Surbiton"},
}

NUM_ROWS = 10          # rows requested from the board per call
TIME_WINDOW = 120      # minutes of timetable requested per call
MIN_OFFSET, MAX_OFFSET = -60, 119
PAGE_SIZE_DEFAULT = 7


# --------------------------------------------------------------------------- helpers

def g(d, *keys, default=None):
    """First non-null value among several possible key spellings."""
    if isinstance(d, dict):
        for k in keys:
            if d.get(k) is not None:
                return d[k]
    return default


TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})")


def parse_hhmm(value):
    if not isinstance(value, str):
        return None
    m = TIME_RE.match(value.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return h, mi


def clock(value):
    """'18:04*' -> '18:04'; non-times return None."""
    p = parse_hhmm(value)
    return f"{p[0]:02d}:{p[1]:02d}" if p else None


def to_dt(hhmm, ref):
    """Place an HH:MM on the timeline nearest to ref (handles midnight)."""
    h, m = parse_hhmm(hhmm)
    dt = ref.replace(hour=h, minute=m, second=0, microsecond=0)
    if dt - ref < -timedelta(hours=6):
        dt += timedelta(days=1)
    elif dt - ref > timedelta(hours=18):
        dt -= timedelta(days=1)
    return dt


def minutes_between(a_hhmm, b_hhmm):
    """Signed minutes from a to b, both HH:MM, tolerant of midnight."""
    a, b = parse_hhmm(a_hhmm), parse_hhmm(b_hhmm)
    diff = (b[0] * 60 + b[1]) - (a[0] * 60 + a[1])
    if diff > 720:
        diff -= 1440
    elif diff < -720:
        diff += 1440
    return diff


def to_int(value):
    try:
        n = int(value)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def clean_text(value):
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def location_names(items):
    out = []
    for it in items or []:
        name = g(it, "locationName", "location_name")
        if not name:
            continue
        via = clean_text(g(it, "via", default=""))
        out.append(f"{name} {via}".strip())
    return out


# --------------------------------------------------------------------------- normalising

def expected_time(planned, estimate, actual):
    """Return (expected_hhmm_or_None, state) for a calling point or departure."""
    at = clock(actual)
    if at:
        return at, "actual"
    est = clock(estimate)
    if est:
        return est, "estimated"
    text = (estimate or "").strip().lower() if isinstance(estimate, str) else ""
    if text == "on time":
        return clock(planned), "on_time"
    if text == "cancelled":
        return None, "cancelled"
    if text in ("delayed", "no report"):
        return None, "unknown"
    return None, "unknown"


def pick_calling_points(svc):
    """First usable group of subsequent calling points (skips changes of service)."""
    groups = g(svc, "subsequentCallingPoints", default=[]) or []
    for grp in groups:
        if g(grp, "serviceChangeRequired", default=False) or g(grp, "assocIsCancelled", default=False):
            continue
        points = g(grp, "callingPoint", default=[]) or []
        if points:
            return points
    return []


def normalise_service(svc, dest_crs, now):
    std = clock(g(svc, "std"))
    if not std:
        return None
    service_type = g(svc, "serviceType")
    if service_type and str(service_type).lower() != "train":
        return None

    etd_raw = g(svc, "etd", default="")
    etd_text = etd_raw.strip().lower() if isinstance(etd_raw, str) else ""
    cancelled = bool(g(svc, "isCancelled", default=False)) or etd_text == "cancelled"
    part_cancelled = bool(g(svc, "filterLocationCancelled", default=False)) and not cancelled

    dep_expected, dep_state = expected_time(std, etd_raw, g(svc, "atd"))
    delay = 0
    if cancelled:
        status = "cancelled"
    elif part_cancelled:
        status = "part_cancelled"
    elif dep_state == "unknown":
        status = "delayed"
    else:
        delay = minutes_between(std, dep_expected) if dep_expected else 0
        status = "late" if delay > 0 else "on_time"

    stops = []
    for cp in pick_calling_points(svc):
        st = clock(g(cp, "st"))
        exp, state = expected_time(g(cp, "st"), g(cp, "et"), g(cp, "at"))
        stops.append({
            "name": g(cp, "locationName", default=g(cp, "crs", default="")),
            "crs": g(cp, "crs", default=""),
            "planned": st,
            "expected": exp if exp and exp != st else None,
            "state": state,
            "cancelled": bool(g(cp, "isCancelled", default=False)),
            "length": to_int(g(cp, "length")),
        })
    idx = next((i for i, s in enumerate(stops) if s["crs"] == dest_crs), None)
    arrival = None
    if idx is not None:
        dest_stop = stops[idx]
        stops = stops[:idx + 1]
        arrival = {
            "planned": dest_stop["planned"],
            "expected": dest_stop["expected"],
            "state": dest_stop["state"],
            "cancelled": dest_stop["cancelled"] or cancelled or part_cancelled,
        }

    length = to_int(g(svc, "length"))
    if length is None:
        for s in reversed(stops):
            if s["length"]:
                length = s["length"]
                break

    reason = clean_text(g(svc, "cancelReason", default="")) if (cancelled or part_cancelled) else ""
    if not reason:
        reason = clean_text(g(svc, "delayReason", default=""))

    std_dt = to_dt(std, now)
    dests = location_names(g(svc, "destination", default=[]))
    origins = location_names(g(svc, "origin", default=[]))
    plat = g(svc, "platform")
    return {
        "id": g(svc, "serviceID", "serviceId", default=f"{std}-{dests[0] if dests else ''}"),
        "planned": std,
        "expected": dep_expected if dep_expected and dep_expected != std else None,
        "in_min": int((std_dt - now).total_seconds() // 60),
        "status": status,
        "delay_min": delay,
        "platform": str(plat) if plat not in (None, "") else None,
        "operator": g(svc, "operatorCode", default=None) or g(svc, "operator", default=""),
        "operator_name": g(svc, "operator", default=""),
        "origin": origins[0] if origins else "",
        "destination": dests[0] if dests else "",
        "length": length,
        "reason": reason,
        "arrival": arrival,
        "stops": stops,
        "stop_count": max(len(stops) - 1, 0) if arrival else len(stops),
    }


def normalise_board(board, dest_crs, now):
    """Raw Darwin board JSON -> list of services (sorted by planned departure) and messages."""
    if not isinstance(board, dict):
        raise ValueError("Board response was not an object")
    for key in ("error", "errors", "fault"):
        if board.get(key):
            raise ValueError(f"Rail Data returned an error: {json.dumps(board[key])[:200]}")
    raw = board.get("trainServices")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ValueError("trainServices was not a list")
    services = [s for s in (normalise_service(r, dest_crs, now) for r in raw) if s]
    services.sort(key=lambda s: s["in_min"])
    messages = []
    for m in board.get("nrccMessages") or []:
        text = clean_text(g(m, "value", default=m if isinstance(m, str) else ""))
        if text:
            messages.append(text)
    return services, messages[:3]


def build_page(services, messages, offset, page_size, now):
    """Pick a page of services and work out the cursor for the next page."""
    shown = services[:page_size]
    next_offset = None
    has_next = False
    if shown and len(services) > page_size:
        last_in = shown[-1]["in_min"]
        candidate = max(offset + 1, last_in + 1)
        if candidate <= MAX_OFFSET:
            next_offset, has_next = candidate, True
    return {"services": shown, "messages": messages, "offset": offset,
            "next_offset": next_offset, "has_next": has_next}


# --------------------------------------------------------------------------- upstream

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


class UpstreamError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def fetch_board(base_url, api_key, crs, filter_crs, offset):
    parsed = urllib.parse.urlparse(base_url)
    if (parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST or parsed.port
            or parsed.username or parsed.query or parsed.fragment):
        raise UpstreamError(f"RAIL_DATA_BASE_URL must be an https URL on {ALLOWED_HOST}")
    query = urllib.parse.urlencode({
        "numRows": NUM_ROWS, "filterCrs": filter_crs, "filterType": "to",
        "timeOffset": offset, "timeWindow": TIME_WINDOW,
    })
    url = f"{base_url.rstrip('/')}/GetDepBoardWithDetails/{urllib.parse.quote(crs)}?{query}"
    req = urllib.request.Request(url, headers={
        "x-apikey": api_key, "Accept": "application/json", "User-Agent": "TrainTimesBoard/1.0"})
    try:
        with _OPENER.open(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise UpstreamError("Rail Data rejected the API key. Check RAIL_DATA_API_KEY and that you "
                                "subscribed to the Live Departure Board product.", e.code)
        if e.code == 429:
            raise UpstreamError("Rail Data rate limit reached. Try again shortly.", 429)
        if e.code == 404 or e.code == 500:
            raise UpstreamError("Rail Data could not route the request. Check RAIL_DATA_BASE_URL against "
                                "the product's Specification tab.", e.code)
        raise UpstreamError(f"Rail Data returned HTTP {e.code}.", e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpstreamError(f"Could not reach Rail Data: {getattr(e, 'reason', e)}")
    except ValueError:
        raise UpstreamError("Rail Data returned something that was not JSON.")


# --------------------------------------------------------------------------- demo data

_MOCK_STOPS = {
    "out": {
        "fast": [("Clapham Junction", "CLJ", 14), ("London Waterloo", "WAT", 22)],
        "slow": [("New Malden", "NEM", 4), ("Raynes Park", "RAY", 7), ("Wimbledon", "WIM", 11),
                 ("Earlsfield", "EAR", 15), ("Clapham Junction", "CLJ", 18), ("Vauxhall", "VXH", 22),
                 ("London Waterloo", "WAT", 26)],
        "dests": ["London Waterloo"],
    },
    "back": {
        "fast": [("Clapham Junction", "CLJ", 8), ("Surbiton", "SUR", 21), ("Woking", "WOK", 33)],
        "slow": [("Vauxhall", "VXH", 4), ("Clapham Junction", "CLJ", 8), ("Earlsfield", "EAR", 12),
                 ("Wimbledon", "WIM", 16), ("Raynes Park", "RAY", 19), ("New Malden", "NEM", 22),
                 ("Surbiton", "SUR", 26), ("Hampton Court", "HMC", 32)],
        "dests": ["Woking", "Alton", "Portsmouth Harbour", "Southampton Central"],
    },
}


def _fmt(dt):
    return dt.strftime("%H:%M")


def mock_board(route, offset, now):
    """Fake board in the same shape as the real API, so it exercises the real parser."""
    cfg = ROUTES[route]
    plan = _MOCK_STOPS[route]
    start = now.replace(second=0, microsecond=0) + timedelta(minutes=2)
    gaps = [0, 7, 8, 7, 8, 7, 8, 7, 8, 7, 8, 7, 8, 7, 8, 7, 8, 7, 8, 7, 8, 7, 8, 7, 8, 7, 8, 7]
    services = []
    t = start - timedelta(minutes=70)
    for i, gap in enumerate(gaps):
        t += timedelta(minutes=gap or 0)
        mins = (t - now).total_seconds() / 60
        if mins < offset or mins > offset + TIME_WINDOW:
            continue
        kind = i % 7
        stops = plan["fast"] if i % 2 == 0 else plan["slow"]
        dest_name = plan["dests"][i % len(plan["dests"])]
        svc = {
            "serviceID": f"mock{i}", "std": _fmt(t), "etd": "On time",
            "operator": "South Western Railway", "operatorCode": "SW", "serviceType": "train",
            "platform": str(1 + (i % 4)), "isCancelled": False, "length": [10, 8, 5, 12][i % 4],
            "origin": [{"locationName": cfg["from_name"], "crs": cfg["from"]}],
            "destination": [{"locationName": dest_name, "crs": "XXX"}],
            "subsequentCallingPoints": [{"callingPoint": [
                {"locationName": n, "crs": c, "st": _fmt(t + timedelta(minutes=d)),
                 "et": "On time", "isCancelled": False} for n, c, d in stops]}],
        }
        if kind == 2:
            late = 4 + (i % 3) * 3
            svc["etd"] = _fmt(t + timedelta(minutes=late))
            for cp in svc["subsequentCallingPoints"][0]["callingPoint"]:
                cp["et"] = _fmt(datetime.strptime(cp["st"], "%H:%M") + timedelta(minutes=late))
            svc["delayReason"] = "A fault with the signalling system"
        elif kind == 4:
            svc["etd"] = "Cancelled"
            svc["isCancelled"] = True
            svc["cancelReason"] = "This train has been cancelled because of a shortage of train crew"
            for cp in svc["subsequentCallingPoints"][0]["callingPoint"]:
                cp["et"] = "Cancelled"
                cp["isCancelled"] = True
        elif kind == 5:
            svc["etd"] = "Delayed"
            svc["platform"] = None
            svc["delayReason"] = "Trespassers on the railway"
            for cp in svc["subsequentCallingPoints"][0]["callingPoint"]:
                cp["et"] = "Delayed"
        services.append(svc)
        if len(services) >= NUM_ROWS:
            break
    return {"locationName": cfg["from_name"], "crs": cfg["from"], "trainServices": services,
            "nrccMessages": [{"value": "Demo data only. Add your Rail Data key to see live trains."}]}


# --------------------------------------------------------------------------- app

class Board:
    def __init__(self):
        self.key = os.environ.get("RAIL_DATA_API_KEY", "").strip()
        self.base = os.environ.get("RAIL_DATA_BASE_URL", DEFAULT_BASE).strip()
        self.demo = os.environ.get("MOCK", "").strip() == "1" or not self.key
        self.ttl = float(os.environ.get("CACHE_TTL", "30"))
        self._cache = {}
        self._lock = threading.Lock()

    def get(self, route, offset, page_size, now=None):
        now = now or datetime.now(LONDON)
        cfg = ROUTES[route]
        out = {"route": route, "title": cfg["title"], "from": cfg["from_name"], "to": cfg["to_name"],
               "mode": "demo" if self.demo else "live", "generated_at": now.isoformat(timespec="seconds"),
               "stale": False, "error": None}
        key = (route, offset)
        if self.demo:
            board = mock_board(route, offset, now)
        else:
            with self._lock:
                hit = self._cache.get(key)
            if hit and time.time() - hit[0] < self.ttl:
                board = hit[1]
            else:
                try:
                    board = fetch_board(self.base, self.key, cfg["from"], cfg["to"], offset)
                    normalise_board(board, cfg["to"], now)       # validate before caching
                    with self._lock:
                        self._cache[key] = (time.time(), board)
                except (UpstreamError, ValueError) as e:
                    if hit and time.time() - hit[0] < 900:
                        board, out["stale"], out["error"] = hit[1], True, str(e)
                    else:
                        out.update({"services": [], "messages": [], "offset": offset, "next_offset": None,
                                    "has_next": False, "error": str(e)})
                        return out
        services, messages = normalise_board(board, cfg["to"], now)
        out.update(build_page(services, messages, offset, page_size, now))
        return out


BOARD = Board()
INDEX = (HERE / "static" / "index.html")


class Handler(BaseHTTPRequestHandler):
    server_version = "TrainTimes/1.0"

    def log_message(self, fmt, *args):   # quiet, one line per request
        print("%s %s" % (self.address_string(), fmt % args), flush=True)

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        elif parsed.path == "/api/health":
            self._send(200, json.dumps({"ok": True, "mode": "demo" if BOARD.demo else "live"}))
        elif parsed.path == "/api/board":
            q = urllib.parse.parse_qs(parsed.query)
            route = (q.get("route") or ["out"])[0]
            if route not in ROUTES:
                return self._send(400, json.dumps({"error": "Unknown route"}))
            try:
                offset = max(MIN_OFFSET, min(MAX_OFFSET, int((q.get("offset") or ["0"])[0])))
                n = max(1, min(NUM_ROWS, int((q.get("n") or [str(PAGE_SIZE_DEFAULT)])[0])))
            except ValueError:
                return self._send(400, json.dumps({"error": "offset and n must be whole numbers"}))
            self._send(200, json.dumps(BOARD.get(route, offset, n)))
        else:
            self._send(404, json.dumps({"error": "Not found"}))


def check(raw=False):
    """Fetch one live board and print what the parser makes of it. Use once the key arrives."""
    if BOARD.demo:
        print("No RAIL_DATA_API_KEY set (or MOCK=1). Set the key to run a live check.")
        return 2
    cfg = ROUTES["out"]
    now = datetime.now(LONDON)
    try:
        board = fetch_board(BOARD.base, BOARD.key, cfg["from"], cfg["to"], 0)
    except UpstreamError as e:
        print("FAILED:", e)
        return 1
    print("Top-level keys:", sorted(board) if isinstance(board, dict) else type(board).__name__)
    if raw:
        first = (board.get("trainServices") or [None])[0] if isinstance(board, dict) else None
        print(json.dumps(first, indent=2))
    try:
        services, messages = normalise_board(board, cfg["to"], now)
    except ValueError as e:
        print("PARSE FAILED:", e)
        return 1
    print(f"{len(services)} direct services {cfg['from_name']} to {cfg['to_name']}")
    for s in services[:7]:
        arr = s["arrival"] or {}
        print(f"  {s['planned']} {s['status']:<14} plat {s['platform'] or '-':<3} "
              f"arr {arr.get('planned') or '--:--'} cars {s['length'] or '?':<3} stops {s['stop_count']}")
    if services and not any(s["length"] for s in services):
        print("Note: no carriage counts in this feed; the board hides them when absent.")
    return 0


def main():
    if "--check" in sys.argv or "--raw" in sys.argv:
        raise SystemExit(check(raw="--raw" in sys.argv))
    port = int(os.environ.get("PORT", "8099"))
    mode = "demo data" if BOARD.demo else "live Rail Data"
    print(f"Train times board on :{port} ({mode})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
