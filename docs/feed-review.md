# Live feed review — 2026-10-30

AGENTS.md's verified feed facts are authoritative. The complete captures from
commit 2ebd7d5 are moved unchanged from rail-fixtures into tests/fixtures:

- sur-wat.json: ten services, generated 2026-10-30T19:27:45.1386272+00:00.
- wat-sur.json: ten services, generated 2026-10-30T19:27:45.356788+00:00.

No new key or live network request was needed. The old synthetic board.json is
removed. Small in-code synthetic records remain only for logic absent from the
captures, such as HH:MM delay estimates, midnight and partial-cancellation groups.

## Differences and fixes

| Area | Previous code versus the captures / verified facts | Resolution |
|---|---|---|
| Field casing | Normaliser, provider board recognition and raw CLI selected exact-case keys; AGENTS requires case-insensitive reads at every nesting level | Shared case-insensitive lookup, including timestamps, notices, nested groups/calls and cancellation reasons; preserve original raw JSON |
| Platform | Waterloo omits platform on seven services, including the cancellation, even though platformAvailable is true; these became null/omitted | Missing/empty platform becomes TBC |
| Request rows | Provider requested 50 rather than the verified numRows=10 request in AGENTS | Request 10; no constant-only test |

The current complete captures use `On time`, `Cancelled` and canonical field
casing apart from capital `Value`; no additional estimate spelling is assumed.

## Already correct; no duplicate fixes/tests

- Surbiton nrccMessages items use capital **Value**, already read correctly. Waterloo
  has no nrccMessages; absent/null notices were already tolerated. The casing
  regression also checks notice extraction, so a separate Value-only test adds nothing.
- Each board contains one cancellation with service/calling-point length **0**.
  Zero already became unknown and was omitted from API JSON. Positive service
  counts range from 4 to 12; destination/stop lengths are not used to guess the
  departure formation. The real-fixture test covers both counts and omission.
- Destination arrival is already selected by calling-point CRS. Waterloo→Surbiton
  journeys continue past Surbiton; the stop list is correctly truncated there.
- Surbiton's 20:01 and Waterloo's 19:23 services have etd=Cancelled,
  isCancelled/filterLocationCancelled=true and a crew-shortage cancelReason. Their
  status, reason and cancelled arrival already parse correctly. Separate synthetic
  on-time/cancellation tests are removed because the capture test now covers them.
- generatedAt carries an explicit UTC offset and six/seven fractional digits.
  Python already parses this, representing microseconds (six fractional digits).
- `On time` uses the planned time and on_time state; duplicate expected timestamps
  are deliberately omitted. This is normalisation, not loss of the arrival time.

Present but intentionally not exposed as separate application fields:

- Board: Xmlns, locationName/crs, filterLocationName/filtercrs/filterType and
  platformAvailable. Route config supplies board labels; platformAvailable does
  not promise that every service has a platform.
- Service: futureCancellation/futureDelay, isCircularRoute, detachFront,
  isReverseFormation and rsid. Origin/destination arrays become display names;
  their CRS and assocIsCancelled metadata are not copied into those display strings.
- Calls: detachFront, affectedByDiversion and rerouteDelay. Group serviceType,
  serviceChangeRequired and assocIsCancelled guide selection rather than being
  copied into the flattened destination-specific stop list.

No new future-cancellation/formation/diversion UI is added by this patch.

## Prompt 2 scope status

Delivered: RDM REST operation/parameters, server-only environment/file key,
whitespace stripping on environment/file input, exact-host HTTPS allowlist,
redirect rejection, 15-second network timeout, 2 MB size cap, per-pair/offset TTL
cache, per-key coalescing, up-to-900-second stale/error metadata, safe error mapping,
station search, atomic validated route CRUD/return option, optional ADMIN_TOKEN,
length-only carriages, --check/--raw and quota budgeting. Docker/Portainer variables
and the existing Docker Hub publication workflow remain in place.

This review now verifies both complete board responses through provider parsing
and normalisation. One test checks all twenty destination arrival times, both
cancellations and carriage counts; two focused regressions cover case-insensitive
field reads and TBC platforms. No network, transport mocks or new test tooling.

Not completed/proven, and deliberately not implemented here:

- Retrieval of current official ldbws.json and verification of runtime numeric
  ranges. The schema mirror has no numeric bounds; the app's -60..119 offsets
  still exceed the single offset=0 example verified in AGENTS.
- A hard 15-second wall-clock deadline: urllib's timeout is a connect/socket
  inactivity timeout. Slow trickle responses can take longer.
- A live exercise of this client's transport, concurrent request coalescing and
  stale-on-error behaviour. Fixture parsing does not establish those behaviours.
- Refilling a truncated 10-row board for large custom page sizes/walking filters;
  the standard seven-row page fits the verified request. Minute cursors retain
  the prototype's known equal-minute boundary limitation.

The final board UI/editor and station autocomplete UI remain later-phase work;
Prompt 2 delivered API endpoints and a minimal preview, not those screens.
