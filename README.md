# Rail

A small home-server departure board. Phase 2 adds the RDM REST provider, memory
caching, station search and persisted route management. The page remains a minimal
API preview; the final departure-board UI is a later phase.

## Run

Python 3.12 and system timezone data are required (included in the Docker image).

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
RAIL_DATA_PATH="$PWD/work/data" uvicorn app.main:app --host 127.0.0.1 --port 8080 --no-access-log --log-config app/logging.json
```

Open http://localhost:8080. With no key/file configured, `RAIL_PROVIDER=auto`
(default) uses clearly labelled synthetic Demo boards. Demo includes delays,
cancellations, variable lengths, missing platforms and replacement buses. It never
represents real trains. `demo` forces Demo; `rail_data` explicitly requests live.
An invalid configured key/base URL produces an error, never a silent Demo fallback.

## Live feed

Set these as Portainer stack variables; `.env.example` documents the whole surface:

- RAIL_DATA_BASE_URL: copy the complete base ending `/LDBWS/api/20220120` from the
  subscribed public Live Departure Board product's Specification tab. No guessed
  default is supplied. Do not append the operation or station yourself.
- RAIL_DATA_API_KEY: the consumer key, **or** RAIL_DATA_API_KEY_FILE: an already
  mounted container file containing the key (readable by UID 10001). Never both.
- RAIL_DATA_ALLOWED_HOSTS: exact comma-separated host allowlist; default
  `api1.raildata.org.uk`. Add a different host only if the subscribed Specification
  actually uses it. HTTPS only; no custom port, credentials, query or fragment.
- RAIL_CACHE_TTL and RAIL_REFRESH_SECONDS: default 30; integer 5–300 seconds.

The standard stack uses environment credentials. Secret-file mode requires a
read-only file mount/deployment override (for example a Docker secret mounted at
`/run/secrets/rail_api_key`) and RAIL_DATA_API_KEY_FILE set to that container path.
The repository never contains the file; Compose does not create or copy it.
Keep it readable by UID/GID 10001. Restart to reload credentials/settings.

Requests use server-side `x-apikey`, no redirects, a 15-second network timeout and
a 2,000,000-byte response limit. The timeout is urllib's connect/socket inactivity
timeout, not a guarantee against an indefinitely slow trickle response. No key or
raw provider exception is sent to the browser or normal logs. See the outstanding
[contract verification and fixture inspection](docs/feed-contract.md).

Cache key: (origin, destination, offset). TTL is shared across clients, concurrent
requests coalesce, errors have retry cooldowns and stale-on-error retains the last
good board for at most 15 minutes **from its successful fetch**. The API exposes
`stale`, `error`, `error_code`, `cache_age_seconds` and feed `generated_at`; the
preview labels stale boards visibly. Older boards are not served after an error.
Only validated boards enter the cache. The cache holds up to 256 completed entries
and is in memory only. Run one worker. See the [5-million-call budget](docs/api-budget.md).

Missing platforms are shown as `TBC`. Feed field names are read case-insensitively.
Missing or non-positive carriage counts are omitted; only the feed's `length` is
used. Stop-specific lengths do not become departure carriage counts. No guessing.

## One-request diagnostics

When your key arrives, run inside the configured container:

```sh
python -m app --check
python -m app --check --raw
python -m app --check --route back --raw
```

Each command makes one live detailed-board request, even when the app otherwise
runs in Demo. It prints the parsed board and optionally the first raw service;
nonzero exit means failure. It never prints request headers or the key. Raw output
is for deliberate local diagnostics, not general logging. The user supplied live response captures, now checked through parsing/normalisation;
this client's live transport and runtime parameter limits have not yet been exercised.

## Routes are runtime data

Load `${RAIL_DATA_PATH}/routes.json` (default `/data/routes.json`). The default
routes are SUR→WAT and WAT→SUR, labelled with their station names. A missing,
unreadable, malformed, oversized or unsupported file falls back safely, without
writing over that file; `/api/health` reports the fallback category. Explicitly
empty routes stay empty. The API now persists edits immediately, and restart
loads them. Manual file edits require restart. Never put this file in Git/image.

```json
{
  "version": 1,
  "routes": [{
    "id": "out",
    "label": "Surbiton to London Waterloo",
    "origin": "SUR",
    "destination": "WAT",
    "min_departure_minutes": 8,
    "page_size": 7
  }]
}
```

Limits: 0–32 routes, unique 1–64-character ASCII letter/digit/underscore/hyphen IDs
starting with a letter/digit, visible labels up to 100 characters, distinct uppercase
three-letter catalogue CRS codes, walking time 0–120 (default 0), page size 1–25
(default 7), version 1 and a 256,000-byte config limit. Unknown fields, booleans or
strings masquerading as numeric route settings are rejected.

## API

| Endpoint | Behaviour |
|---|---|
| GET /api/health | Local responsiveness, provider configuration readiness, config source/warning and preview refresh interval; no upstream call |
| GET /api/routes | Saved route records in order |
| POST /api/routes | Create a route from a JSON route record; optional `add_return_journey: true`; returns complete saved list, HTTP 201 |
| PUT /api/routes | Replace the route identified by the JSON record's `id`; same optional return flag; returns complete saved list |
| DELETE /api/routes?id=out | Remove one saved route; returns complete saved list |
| GET /api/stations?q=waterloo | Case-insensitive CRS/name search, code/name prefixes and word prefixes; at most 10 results |
| GET /api/board?route=out&offset=0 | Normalised board and freshness/error metadata |

An example POST body is a route object as above, with `add_return_journey: true`.
A reverse route gets `<first 48 ID characters>-return`, a station-name label,
reversed CRS codes and copied page-size/walking settings. An already saved return
pair or ID conflict is rejected. Both routes are validated and atomically saved
in one operation; neither is partially created. Edit the return's walking time
separately if it differs. PUT uses the complete replacement record; DELETE can
leave an intentionally empty list. Duplicate ID/return conflicts return 409,
unknown route 404, invalid parameters/payloads 422 and persistence failure 503.
Failed saves retain previous in-memory configuration. Concurrent writes serialise;
updates to the same route are last-write-wins.

Route is required for a board. Offset is an integer -60..119 (default 0), unknown
or repeated query parameters are rejected. A 120-minute window is paged by the
prototype cursor (last displayed departure minute + 1, capped at 119). Earlier
initially requests -45; the preview remembers previous offsets. Walking time
filters current/future scheduled departures, not the historical Earlier window.
These are moving windows, not snapshots; same-minute boundary trains can be
skipped. Runtime RDM limits remain to be confirmed as documented in the contract note.

Upstream failures have safe error codes: `authentication` (401/403 upstream),
`rate_limit` (429), `routing` (400/404/500), `timeout`, `bad_json`, `response_size`,
`redirect`, `connection` or `upstream`. The app returns 502/503/504 as appropriate,
with Retry-After; upstream authentication failure is not confused with app login.
A stale fallback remains HTTP 200 with explicit stale/error metadata.

The catalogue is the approved phase-1 [Trainline GB ODbL snapshot](app/data/README.md)
with 2,652 entries. Its licence and transformation are shipped in the image.
Membership does not establish active service or Darwin coverage; Northern Ireland
coverage and intermediate-destination behaviour need live review.

## Access and deployment

There is no app login. Remote access **must** be protected by Cloudflare Access.
Without ADMIN_TOKEN all users who can reach the app can edit routes. Set the
optional ADMIN_TOKEN to require `Authorization: Bearer <token>` for POST/PUT/DELETE.
It does not affect reads and is not a substitute for Access. The preview does not
contain a token or a route editor; use authenticated API calls for now.

`compose.yaml` uses Portainer variables, host port 8097, a local named `rail-data`
volume at /data, restart unless-stopped, TZ=Europe/London and linux/amd64. No NAS,
edge-network attachment or TLS listener. Ingress stays Access → Tunnel → shared
Caddy → minisforum.lan:8097. Keep that host port off the public internet.
The image listens on container port 8097, runs as UID/GID 10001, and is read-only
except /data and the /tmp tmpfs. A fresh volume inherits
its ownership. Back up only routes.json; keep restored files readable by that UID.

CI retains the merged deployment workflow: Ruff and pytest on pull requests;
validated pushes to main build and publish Docker Hub tags `main` and
`sha-<7-character-commit>`. Superseded runs are cancelled and jobs have a five-minute
timeout. No Portainer webhook or automatic stack action is added. Watchtower may
update containers tracking `main`; use an immutable SHA tag for deliberate releases.

First deployment:

1. Create the `rail` Docker Hub repository and configure GitHub Actions secrets
   DOCKERHUB_USERNAME and DOCKERHUB_TOKEN with publishing permission.
2. After merging, wait for the main workflow to publish the image.
3. In Portainer, create a Repository stack from `jonesdavidj/rail`, branch `main`,
   Compose path `compose.yaml`. Configure read access if the GitHub repo or image
   is private.
4. Set DOCKERHUB_USERNAME and RAIL_IMAGE_TAG in stack variables; `.env.example`
   documents all names/defaults. Use the published SHA tag for a deliberate release.
   The stack defaults to Demo; no Rail Data key is needed to start.
5. Deploy and verify `/api/health` on host port 8097. Preserve `rail-data` on updates.
6. For live validation, set the key and Specification base URL as Portainer variables,
   run `python -m app --check --raw` in the container, and then select
   RAIL_PROVIDER=auto or rail_data when ready. Do not commit or send the key in chat.

## Checks and testing policy

```sh
python -m ruff check app tests scripts/bundle_stations.py
python -m ruff format --check app tests scripts/bundle_stations.py
python -m pytest
./scripts/check.sh  # also needs Docker Compose, Hadolint and Gitleaks
```

Tests are focused on normalisation, midnight/arrival/cancellation, paging, config
and error mapping, with two complete live fixtures and minimal in-code examples for uncovered branches. They block network access.
No browser suite, snapshots, coverage gates, type checker or transport/concurrency
harness. A single Demo container smoke check is used locally when validating image changes.
CI retains main's lean Ruff/pytest and Docker Hub publication workflow. Existing broad phase-1 matrices
and trivial framework/logging tests were removed to follow the current policy.
Dependencies remain pinned; application and Uvicorn logs are JSON without raw
paths, query strings, credentials or payloads. ADRs are in docs/adr/.
