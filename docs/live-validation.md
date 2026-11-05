# Live validation — 2026-10-30

## Evidence and changes

The managed workspace cannot reach `rail.balaclavaroad.com`: its outbound proxy
rejects CONNECT with 403, before Cloudflare/the app. No VPN or live key is configured
here. **No current live UI/feed comparison or measured upstream rate is claimed.**
The existing two live captures are historical evidence, not today's deployment.

Local checks reproduced and fixed these paging defects:

- `last departure minute + 1` dropped other services in that minute. Cursor now
  includes the absolute departure and service ID; the boundary minute is fetched
  inclusively and already shown rows excluded.
- A relative offset drifted when the clock advanced between clicks. The cursor
  fixes the time boundary, including across midnight, and expires after 15 minutes.
- A full ten-row upstream response was mistaken for the end of the timetable.
  Continue when capped; a final empty page is possible because the feed has no
  total count. A cursor walk stays within two hours of its first page; Earlier
  starts 45 minutes back.
- At 19:27:45 the existing SUR fixture's 19:27 service became `in_min=-1` and was
  filtered out. Use minute precision consistently, including Demo window selection.

Five focused regressions cover these differences; existing walking-time paging
expectations were updated. No new feed fixture or speculative parsing change.
Date-less HH:MM still cannot disambiguate the autumn repeated hour. Nor can a
live, row-limited feed guarantee an immutable list: withdrawn/inserted services,
changed IDs, or more than ten services in one departure minute need real evidence
and may require upstream capabilities beyond this endpoint. Runtime offset limits
(-45 through 119) still need live confirmation.

## Capture on the home server / LAN (Bash)

No Access or ingress changes needed. Use https://rail-lan.balaclavaroad.com (LAN only); do not publish a host port.
These commands save board JSON only, never the key. First inspect route IDs; replace
`out`/`back` below if they changed. Keep capture files outside Git unless a novel
case is selected and sanitised later.

```bash
mkdir -p rail-validation
curl --fail-with-body --max-time 20 https://rail-lan.balaclavaroad.com/api/health -o rail-validation/health.json
curl --fail-with-body --max-time 20 https://rail-lan.balaclavaroad.com/api/routes -o rail-validation/routes.json
```

Run the following mid-minute, with the subscribed Specification base URL. Enter
only the consumer key at the hidden prompt; do not paste it into chat or a file.
The key is passed to curl through stdin, not its command-line arguments. There
are two direct RDM calls; API calls may also cause cache misses. Do not use `-v`.

```bash
read -r -s -p 'RDM consumer key: ' RAIL_CHECK_KEY; printf '\n'
RAIL_CHECK_BASE='https://api1.raildata.org.uk/1010-live-departure-board-dep1_2/LDBWS/api/20220120'
for pair in sur-wat wat-sur; do
  if [ "$pair" = sur-wat ]; then from=SUR; to=WAT; route=out; else from=WAT; to=SUR; route=back; fi
  curl --fail-with-body --max-time 20 --get https://rail-lan.balaclavaroad.com/api/board \
    --data-urlencode "route=$route" --data-urlencode offset=0 -o "rail-validation/$pair-app-before.json"
  printf 'x-apikey: %s\n' "$RAIL_CHECK_KEY" | curl --fail-with-body --silent --show-error \
    --max-time 20 --proto '=https' --header @- --header 'Accept: application/json' --get \
    "$RAIL_CHECK_BASE/GetDepBoardWithDetails/$from" --data-urlencode "filterCrs=$to" \
    --data-urlencode filterType=to --data-urlencode timeOffset=0 --data-urlencode timeWindow=120 \
    --data-urlencode numRows=10 -o "rail-validation/$pair-raw.json"
  curl --fail-with-body --max-time 20 --get https://rail-lan.balaclavaroad.com/api/board \
    --data-urlencode "route=$route" --data-urlencode offset=0 -o "rail-validation/$pair-app-after.json"
done
unset RAIL_CHECK_KEY
```

Share the saved JSON responses, not credentials. Compare `generatedAt`/`generated_at`
first: a cached board may be from the previous minute. Match by `serviceID`/`id`;
compare planned/expected departure, status/reason, platform, positive departure
length, destination-CRS arrival and each calling point. Estimates can change even
within one minute: replaying the captured raw response through the normaliser
separates mapping bugs from two different feed snapshots. The UI should then
match its own API response. Novel clock-time delays/buses/short terminations/
service changes are the only reason to add another sanitised fixture.

For current deployment paging, record each response's service IDs and follow its
`next_offset`; after this fix is deployed, also pass its **next_cursor** unchanged:

```bash
curl --fail-with-body --max-time 20 --get https://rail-lan.balaclavaroad.com/api/board \
  --data-urlencode route=out --data-urlencode offset=-45 -o rail-validation/out-earlier.json
curl --fail-with-body --max-time 20 --get https://rail-lan.balaclavaroad.com/api/board \
  --data-urlencode route=out --data-urlencode 'cursor=PASTE_NEXT_CURSOR' -o rail-validation/out-later.json
```

Repeat for `back`, then repeat around 23:50–00:10 London time. Preserve all pages
and raw generation times; check distinct IDs and that the last departure is at
most two hours from the walk's initial minute (service gaps may end it sooner).
The cursor, not a handwritten offset, preserves the boundary after the clock moves.

## Request rate and first-use observations

No upstream counter exists in the app: HTTP request logs include cache hits and
health checks, so they cannot measure RDM calls. Record RDM's per-key usage counter
and UTC time before/after a quiet interval (allow for portal reporting lag). Keep
one visible board for one route, or two clients on different routes, and avoid
manual checks/paging during measurement. For a counter delta D over S seconds:
`calls/hour = D × 3600 / S`; projected four-week calls = `calls/hour × 672`.

Expected, **not observed**, at 30-second refresh/TTL: one active pair ~120/hour
(80,640/28 days, 1.61%); both pairs ~240/hour (161,280, 3.23% of 5 million).
Different offsets, restarts and direct diagnostic calls add traffic; hidden tabs
pause. See [budget assumptions](architecture.md#rail-data-budget-four-weeks).

First-time UI ambiguities visible in existing evidence: Waterloo→Surbiton rows
show the train's ultimate destination (e.g. Guildford) while the arrival column is
for Surbiton; the column heading does not name Surbiton. Stop counts exclude the
selected destination although the expanded list includes it. A capped feed can
produce a final empty Later page. These are observations, not added UI features.
