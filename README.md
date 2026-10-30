# Rail

A small UK departure-board service for a home server. Phase 1 runs entirely on
clearly labelled synthetic Demo data; it does not call RDM or use an API key.

## Run locally

Requires Python 3.12 with system timezone data (the Python slim image includes it).

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
RAIL_DATA_PATH="$PWD/work/data" uvicorn app.main:app --host 127.0.0.1 --port 8080 --no-access-log
```

Open http://localhost:8080 for a minimal JSON-board preview, route selector and
Earlier/Later controls. This is an API proof page, not the final departure-board UI.
No login is implemented. External access must go through Cloudflare Access.

## Runtime route configuration

Configuration is loaded once at startup from `${RAIL_DATA_PATH}/routes.json`
(default `/data/routes.json`). Restart after editing it. No user config is copied
into the image, created at startup, or committed to Git. With a missing, unreadable,
invalid, oversized or unsupported file the app serves the built-in SUR→WAT and
WAT→SUR defaults and reports the fallback category on `/api/health`.
It never replaces the original file. An explicitly empty route list stays empty.

Example file content (write this to your runtime volume, not the source tree):

```json
{
  "version": 1,
  "routes": [
    {
      "id": "out",
      "label": "Surbiton to London Waterloo",
      "origin": "SUR",
      "destination": "WAT",
      "min_departure_minutes": 8,
      "page_size": 7
    },
    {
      "id": "back",
      "label": "London Waterloo to Surbiton",
      "origin": "WAT",
      "destination": "SUR"
    }
  ]
}
```

Limits: 0–32 routes, unique IDs (1–64 ASCII letters/digits/underscore/hyphen,
starting with a letter/digit), visible labels of 1–100 characters without control
characters, distinct uppercase three-letter CRS codes present in the catalogue,
walking time 0–120 minutes (default 0), page size 1–25 (default 7), version 1 and a
256,000-byte file limit. Unknown fields and coerced numbers/booleans are rejected.

The bundled catalogue has 2,652 GB CRS entries derived from Trainline's station
database under ODbL. See [provenance, reproduction and licence](app/data/README.md).
Catalogue membership does not establish current service or Darwin coverage.
Northern Ireland and station search are not delivered in phase 1.

## API

- `GET /api/health`: process health, provider mode/readiness and config source/warning.
  HTTP 200 means the process is serving; inspect `degraded` for config/provider issues.
- `GET /api/routes`: configured route records in tab order.
- `GET /api/board?route=out&offset=0`: normalised services, explicit `demo` flag,
  messages, `generated_at`, `next_offset`, `earlier_offset` and `has_next`.

Route is required. Offset must be an integer from -60 through 119 (default 0).
Malformed, repeated and unknown parameters return 422; an unknown route returns
404; the Rail Data stub returns 503; malformed provider data returns 502.

Providers return the provisional raw Darwin shape; the normaliser returns our own
models. Demo boards are anchored to the current London clock, with stable service
IDs, realistic synthetic timings, late/delayed/cancelled services, absent platforms,
formation variation and replacement buses. All displayed journeys are fictional.
Train and bus rows are explicitly distinguished. Actual times at calling points
are preserved as an `actual` state; unknown times never become invented estimates.
The parser is not claimed to be validated against the current live contract.

## Paging

This phase intentionally follows the prototype's time-offset semantics:

- A board covers 120 minutes relative to the requested offset.
- Return `page_size` rows sorted by scheduled departure and ID.
- If another row is available, `next_offset` is the last displayed departure's
  minutes-from-now plus one (at least the current offset plus one), capped at 119.
- Earlier from the first page requests -45. The preview remembers offsets so
  Earlier from a later page returns to the previous offset.
- Walking time excludes departures closer than the configured minimum on current
  and future pages. It does not filter the explicitly historical Earlier window.

These are moving windows, not snapshots. Minute cursors can skip another service
at the same minute at a page boundary; no historical persistence is provided.
The bounds mirror the prototype and are not verified RDM request limits.

## Checks

```sh
python -m ruff check app tests scripts/bundle_stations.py
python -m ruff format --check app tests scripts/bundle_stations.py
python -m pytest
./scripts/check.sh  # additionally needs Docker Compose, Hadolint and Gitleaks
```

Tests reject network connections/DNS; fixtures and injected clocks are offline.
Prototype test behaviours are ported with intentional corrections listed in ADR 003.
Dependencies, including transitive dependencies, are pinned. Update pins through a PR.
JSON application logs go to stdout with a timestamp, level, event and safe fields.
Raw requests, query strings, authentication headers and payloads are not logged.
Run Uvicorn with `--no-access-log` as the image does.

## Container and deployment

Build locally with `docker build -t rail:local .`. For local Compose verification,
export the documented variables from `.env.example`, setting `RAIL_IMAGE=rail:local`.
Production values belong in Portainer stack variables, not a committed `.env`.

`compose.yaml` publishes host port 8097, uses a local named volume whose name must
be set to `rail-data`, mounts it at `/data`, runs read-only except for that mount,
and uses `restart: unless-stopped`, `TZ=Europe/London` and `linux/amd64` via variables.
A fresh volume inherits `/data` ownership for non-root UID/GID 10001. Restored volumes
must retain readable config permissions. No NAS, external network or TLS listener.

Ingress remains Cloudflare Access → Tunnel → shared edge-caddy →
`minisforum.lan:8097`. The application accepts this Host and uses relative links.
Do not expose the host port to the public internet. You own the Caddy site block.

Phase 1 CI validates, tests, scans, builds and smoke-tests an empty volume. It does
not publish to a registry or deploy. Docker Hub publication with moving `main` and
immutable release tags is deferred; use immutable tags for deliberate Portainer
releases because Watchtower observes moving tags every five minutes.

Set `RAIL_PROVIDER=demo` (default). Explicit `rail_data` selection returns a clear
unimplemented error and degraded health; it never silently serves Demo as live.
RDM authentication, official schema verification, caching and the final UI follow
in later phases. See [ADRs](docs/adr/001-runtime.md).
