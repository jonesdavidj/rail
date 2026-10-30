# Architecture

[Runtime](adr/001-runtime.md), [route config](adr/002-route-config.md),
[normalisation/paging](adr/003-normalisation-and-paging.md) and
[live provider/atomic route writes](adr/004-live-provider-and-route-writes.md).
Later ADRs supersede phase-1 stubs/read-only limits.

main.py is the HTTP boundary; config.py validates models/settings; routes.py owns
atomic JSON persistence; providers.py supplies Demo; rail_data.py implements the
RDM client, shared TTL cache and coalescing. normalise.py maps raw data into
models.py; paging.py builds pages; stations.py searches the bundled catalogue.
__main__.py performs deliberate one-request live diagnostics. The static board and settings sheet use same-origin, framework-free assets;
see [browser ADR](adr/005-browser-board.md). Runtime config and credentials are never image assets.

The optional [Home Assistant adapter](home-assistant.md) lives in
`app/integrations/home_assistant.py`; it consumes the existing provider/cache and
normalised models on demand. No HA dependency, background polling or core feed
change. The app only registers its router and validates its route query.

## Rail Data budget (four weeks)

Quota: **5,000,000 calls per 28 days** (2,419,200 seconds); confirm the subscription's
actual accounting dates in RDM. Built-in routes are SUR→WAT and WAT→SUR; refresh
and shared cache TTL both default to 30 seconds. One fetch obtains the detailed
board, including arrivals/stops: there are no extra per-service calls.

For continuous polling of N distinct route pairs and K offsets per pair at R seconds:
`N × K × ceil(2,419,200 / R)` calls per four weeks, before cache savings.

| Active boards (one offset each) | Calls at 30 seconds | Share of quota |
|---|---:|---:|
| One visible default tab | 80,640 | 1.61% |
| Both configured defaults continuously viewed | 161,280 | 3.23% |
| 32 configured routes continuously viewed | 2,580,480 | 51.61% |

The default two-route budget leaves **4,838,720 calls** spare. Merely saving routes
makes no calls: only the visible tab refreshes, hidden browser tabs pause, and the
server never polls in the background. Identical pair/offset clients share TTL
cache entries and concurrent requests coalesce. Errors have a cooldown; 429 honours
Retry-After. Each deliberate `--check` adds one call.

This is a polling budget, not a hard cap. Earlier/Later offsets are separate keys;
32 pairs × two offsets at 30 seconds would use 5,160,960 calls (103.22%). Extra
clients with staggered requests can approach one call per TTL per active key;
if TTL is below refresh, budget against TTL instead. Restarts, cache evictions,
manual paging/reloads and multiple workers can add calls. Run one worker, avoid
bulk offset polling, monitor RDM usage, and increase both refresh and TTL when
adding many active boards. Demo makes zero Rail Data calls.
