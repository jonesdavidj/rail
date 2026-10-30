# Upstream request budget

Quota supplied for this project: 5,000,000 calls per four-week period. Check the
actual subscription terms when enabling live mode; a rolling 28-day estimate is
not the railway provider's billing-period calendar.

Four weeks = 28 × 24 × 60 × 60 = 2,419,200 seconds. With N distinct configured
origin/destination pairs, K actively refreshed offsets per pair and a refresh
interval R seconds, the polling upper bound for one client per active board is:

    N × K × ceil(2,419,200 / R)

At the default R=30 seconds and TTL=30 seconds:

| Active pairs × offsets | Maximum polling requests / 28 days | Share of 5m |
|---|---:|---:|
| One visible route × 1 | 80,640 | 1.61% |
| Both default routes × 1 | 161,280 | 3.23% |
| 32 routes × 1 | 2,580,480 | 51.61% |
| 32 routes × 2 | 5,160,960 | 103.22% — exceeds quota |

The configured defaults are SUR→WAT and WAT→SUR. The minimal preview refreshes only
its visible route, skips hidden tabs and reads RAIL_REFRESH_SECONDS (default 30).
The server does not poll routes in the background. Saving 32 routes does not by
itself cause 32 upstream calls each interval. --check makes exactly one request.

TTL and coalescing normally share calls across clients at the same pair/offset.
For a resident cache key, no more than ceil(2,419,200 / TTL) successful fetches are
needed; error attempts wait at least max(TTL, error retry delay). HTTP 429 respects
Retry-After (integer seconds or an HTTP date), with a 30-second minimum. There are
no immediate retries or secondary per-service requests. Page size and walking
time are local filters and do not split cache keys; origin/destination/offset do.

**This is a budget, not a hard quota enforcement mechanism.** More clients on
many different pages, 180 possible app offsets, cache eviction after 256 entries,
restarts (which lose the cache), multiple workers/replicas and manual reloads can
increase traffic. For example, refreshing 180 offsets for both default routes
at 30 seconds would request up to 29,030,400 boards from one polling client per
offset. Do not treat the 161,280 default estimate as a universal maximum. Avoid
bulk polling of offsets; increase R/TTL for many active boards and monitor RDM
usage. Do not run multiple Uvicorn workers for this app. If broader use requires a
hard cap, that needs shared durable quota accounting, deliberately outside this
small in-memory app's persistence contract.
