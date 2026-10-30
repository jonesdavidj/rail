# ADR 004: Standard-library RDM client, shared memory cache and atomic routes

Status: implemented; live contract/runtime verification remains outstanding.

Use urllib with a no-redirect handler, an explicit exact-host HTTPS allowlist,
15-second network timeout and a 2 MB body limit. Keys come only from environment
or a readable mounted secret file. Never include a key in URLs, logs or browser
responses. auto mode selects Demo only when no key/file is configured; an invalid
configured live provider reports an error rather than falling back to Demo.

A lock protects an OrderedDict cache and per-key Future map. A leader fetches
outside the lock; clients sharing (origin, destination, offset) await that same
result. Cache only validated boards, re-normalise relative times for each response,
and retain the last good raw board on error. Stale data expires 900 seconds after
its successful fetch; failure does not extend its lifetime. Retry cooldowns and
Retry-After prevent repeated failures hammering the service. Bound completed cache
entries at 256. One Uvicorn worker is required: multiple workers/replicas multiply
upstream traffic and do not share file locks or caches.

RouteStore serialises writes under one lock, validates the whole resulting list,
writes a private temporary file beside routes.json, flushes/fsyncs it and uses
os.replace. Publish in-memory state only after replacement. Add-return is one
operation with one replacement, never two partially successful saves. Editing is
last-write-wins within one process; stale browser revisions are not a distributed
concurrency protocol. No database or NAS dependency.

POST/PUT use validated JSON route records plus optional add_return_journey.
DELETE uses a validated id query. Optional ADMIN_TOKEN protects writes with a
constant-time Bearer comparison. Without it all users who reach the app can edit.
Cloudflare Access remains mandatory for remote access; ADMIN_TOKEN is not a login
system or a substitute for Access. Keep the published port off the public internet.

Testing follows the user's proportionate policy: focused normaliser/paging/config
and error-mapping tests; no transport mocks, contract framework, browser suite,
coverage gate or concurrency harness. Cache/transport mechanics are reviewed
code, not claimed to be validated against a live feed by unit tests.
