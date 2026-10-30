# Darwin/RDM contract inspection — 2026-10-30

This is a one-time manual inspection, not a contract-test suite. The fixture in
`tests/fixtures/board.json` is synthetic and contains no captured live data.

## Evidence and limitation

The official schema URL is:
https://realtime.nationalrail.co.uk/LDBWS/static/ldbws.json

This environment's outbound proxy rejects that host (HTTP CONNECT 403). The web
connector also could not retrieve it. **The current official download and current
RDM Specification-tab deployment limits have not been verified.** No live request
has been attempted because no consumer key is configured. Do not treat Demo or
fixture tests as evidence that a subscription works.

Inspected copy:
https://github.com/darrenparkinson/homeassistant_nationalrail/blob/main/assets/ldbws.json

Exact Git blob: `1f3d4ed143b5397e487d0bf7a2add6d208837ba7` (also inspected in phase 1).
Swagger 2.0, title `20220120.LDBWebService`, version `v1`.
Its `host: localhost`, `schemes: [http]` and basic-auth declaration are deployment
placeholders/legacy metadata: they must not be used for RDM. Use the subscribed
product's HTTPS Specification URL and `x-apikey` as instructed by RDM/user.

## Request inspected

`GET /api/20220120/GetDepBoardWithDetails/{crs}` returns
`#/definitions/StationBoardWithDetails`.

| Parameter | Declared shape/default | Rail sends |
|---|---|---|
| crs | required path string, uppercase | validated route origin |
| filterCrs | optional query string | validated destination |
| filterType | query enum `to` / `from`, default `to` | `to` |
| numRows | query int32, default 10 | 50, to overfetch for page size/walking filter |
| timeOffset | query int32, default 0 | requested app offset (-60..119) |
| timeWindow | query int32, default 120 | 120 |

**This schema copy provides no minimum/maximum for the three integers.** The app's
bounds and values are application policy, not asserted RDM service limits. In
particular the prototype's upper offset 119 and the new 50-row request require
validation against the subscribed Specification tab and a live `--check`. Claims
in other developers' prose about -60..60, 1..50 or 1..300 have not been promoted
to verified facts. If the product rejects a value, show the routing error; do not
silently clamp it or use SOAP. Confirm runtime limits before relying on Later
paging. The `--check` diagnostic currently probes offset 0, not every limit.

The copied filter description refers to origins/destinations. Matching intermediate
calling stations, including Waterloo→Surbiton, remains a key live acceptance check.

## Fixture fields checked by hand

All fields in the single fixture occur in the following copied definitions:

- `StationBoardWithDetails`: generatedAt (date-time), locationName, crs,
  **filtercrs** (response casing), areServicesAvailable, nrccMessages[], trainServices[].
- `NRCCMessage`: **Value** (capital V).
- `ServiceItemWithCallingPoints`: **serviceID**, std, etd, platform, operator,
  operatorCode, isCancelled, **length** (integer), delayReason, origin[],
  destination[], subsequentCallingPoints[].
- `ServiceLocation`: locationName, crs.
- `ArrayOfCallingPoints`: callingPoint[].
- `CallingPoint`: locationName, crs, st, et.

Other parser fields also exist: cancelReason, filterLocationCancelled, serviceType,
previous/subsequentCallingPoints, group serviceChangeRequired/assocIsCancelled,
and calling-point at/isCancelled/cancelReason/length. The parser deliberately
keeps departure `length` separate from stop `length` and never infers a count.
Missing/null/non-positive counts are omitted from JSON, not guessed.

A board's sta/eta concern its board location. Destination arrival is selected from
the appropriate subsequent calling-point group by CRS. The generic st/et/at
calling-point times need live semantic confirmation for intermediate stations.
Dividing/joining services and the repeated autumn clock hour also need real-feed
review; this phase does not claim to resolve ambiguous date-less HH:MM values.

## Differences from the prototype

- Correct nrccMessages[].Value casing; remove its unverified departure atd lookup.
- Fetch 50 rows rather than 10; keep 120-minute windows and prototype offset policy.
- Do not infer departure carriages from downstream calling points.
- Keep unknown estimates unknown; distinguish replacement buses explicitly.
- Preserve feed generatedAt, choose the group containing the selected destination,
  and report partial cancellation when that destination's call is cancelled.
- Add size-limited parsing, bounded shared caching/coalescing and explicit stale
  age/error metadata. Key/base URL are never part of API results or normal logs.

## When a key arrives

1. Read the current public product Specification tab; set its complete operation
   base (ending in `/LDBWS/api/20220120`, without `/GetDepBoardWithDetails`).
2. Retrieve the official schema and compare the above fields and runtime ranges;
   update this note if different. This verification is still outstanding.
3. Set key via Portainer or a mounted secret file. Run
   `python -m app --check --raw` and then `--check --route back --raw`.
4. Check filter behaviour, destination arrival, cancellations/reasons, carriage
   availability, and the configured limits before relying on live operation.
