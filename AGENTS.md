# rail: UK train departure board

Web app showing live departures between UK stations (defaults: Surbiton SUR to London Waterloo WAT and
back). Each saved route is a tab. Python, minimal pinned dependencies. Demo provider works with no key.

## Architecture rules
- Repo: jonesdavidj/rail. It owns its Dockerfile and compose.yaml. Secrets and runtime data never go in Git.
- Flow: pull request, GitHub Actions builds and pushes the image to Docker Hub, then I deliberately
  "Pull and redeploy" a Portainer stack that pulls compose.yaml from this repo. Watchtower also polls Docker
  Hub every 5 minutes and updates running containers.
- compose.yaml is deployed ONLY through a Portainer stack pulled from Git: image only (no `build:`), no
  .env file, no repo-relative mounts, every setting as ${VAR} or ${VAR:-default}, a health check,
  restart: unless-stopped, TZ=Europe/London, container_name rail.
- Image: docker.io/${DOCKERHUB_USERNAME}/rail:${RAIL_IMAGE_TAG:-main}. Use the same Docker Hub secret names
  as my other repos (check jonesdavidj/power-map).
- Ingress is not this repo's job. Cloudflare Access, then cloudflared, then shared Caddy
  (jonesdavidj/proxy) proxies rail.balaclavaroad.com to rail-origin:8097 on external rail_ingress,
  owned by the Docker repo edge stack. The container also publishes configurable host port 8098 for LAN compatibility
  and does not join edge. Keep container/Caddy port 8097; host 8098 avoids Music Assistant stream port 8097. The app must not depend on the Host header.
- The app has no login. Optional ADMIN_TOKEN protects write endpoints.
- State: only the saved route list, as JSON in a local named volume `rail-data` at /data. No NAS volume. The app
  must start on built-in defaults if /data is empty or unreadable, and report that on /api/health.
- Keep it small: standard library or minimal pinned dependencies, non-root, read-only root filesystem,
  cap_drop ALL, no-new-privileges.

## Rail Data Marketplace feed (verified against real responses; fixtures: tests/fixtures/sur-wat.json, wat-sur.json)
- Base URL (env RAIL_DATA_BASE_URL):
  https://api1.raildata.org.uk/1010-live-departure-board-dep1_2/LDBWS/api/20220120
  Request: GET {base}/GetDepBoardWithDetails/{crs}?numRows=10&filterCrs={dest}&filterType=to&timeOffset=0&timeWindow=120
  Header: x-apikey: <consumer key> (env RAIL_DATA_API_KEY). The consumer secret is not used. Strip whitespace
  from the key. Accept: application/json.
- Board keys: Xmlns, areServicesAvailable, crs, filterLocationName, filterType, filtercrs, generatedAt,
  locationName, nrccMessages (absent or null at times), platformAvailable, trainServices. Casing is
  inconsistent (nrccMessages items use "Value"). Read field names case-insensitively.
- Service: subsequentCallingPoints, futureCancellation, futureDelay, origin, destination, std, etd,
  platform (often absent, especially at London Waterloo), operator, operatorCode, isCircularRoute,
  isCancelled, filterLocationCancelled, serviceType, length, detachFront, isReverseFormation, serviceID,
  sometimes cancelReason and rsid.
- Calling point: locationName, crs, st, et, isCancelled, length, detachFront, affectedByDiversion,
  rerouteDelay, sometimes cancelReason. Groups carry serviceType, serviceChangeRequired, assocIsCancelled.
- length is the carriage count; 0 means unknown, so omit it. Missing platform shows "TBC".
- etd seen so far: "On time", "Cancelled". Also handle "Delayed" and HH:MM.
- Arrival at the destination is the calling point whose crs equals the destination.

## Testing policy (keep tests proportionate; this is a small personal app)
- Tests only where a bug would be silent or costly: the feed normaliser (status, delay, cancellation,
  arrival lookup, midnight rollover), paging, config validation. One focused test per behaviour.
- No matrices, snapshots, trivial-code tests, internal mocks, browser test suites or contract suites.
- Tests no larger than about a third of the source. No network in tests.
- Tooling: ruff and pytest only. CI must finish in about a minute.

## Conventions
- Type hints, structured logs, validate all input (CRS must match ^[A-Z]{3}$), text inserted with textContent.
- Small, well-described commits on a branch. Report deviations from these rules instead of silently making them.
