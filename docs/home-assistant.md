# Optional Home Assistant integration

This is a pull-only adapter in `app/integrations/home_assistant.py`. Rail has no HA
library, configuration, connection or background task. Use it only if wanted;
no Home Assistant files are changed by this repo.

## Summary API

`GET /api/summary?route=out&n=7` (use a saved route ID from `/api/routes`) returns:
`n` defaults to 7, accepts 1–10, and limits only the service list, not disruption totals.

- `next_departure`: `id`, timezone-aware ISO `planned` / `expected`,
  `minutes_until_departure`, `status`, `platform`, `carriage_count`; null if none.
- `cancelled_count` / `delayed_count`: all scheduled services in the next 120
  minutes, including those hidden by walking time or UI page size. Cancelled
  includes a cancelled destination call; delayed means `late` or `delayed`, not
  speculative future-delay flags. A service is not counted in both categories.
- `walking_minutes`, `as_of`, oldest feed `generated_at`, `demo`, `stale`, `complete`.
- `services`: the first n scheduled services meeting the walking allowance, including
  cancelled services in their time slots. Each flat row has `id`, ISO `planned` /
  `expected`, `status`, `delay_minutes`, `platform`, `carriage_count`, final
  `destination` (including via text), UTC ISO `arrival_planned` / `arrival_expected`
  at the route destination, `journey_minutes`, `stop_count`, and `fast`.
  No calling points/nested service data. Unknown values are null; on-time delay is
  0 and on-time expected timestamps equal planned. Cancelled rows are never fast.
  Typical n=7 responses from both real captures are about 2.7 KB.

Next means the first scheduled, non-cancelled service meeting the route's saved
walking allowance, matching board order. Its ETA uses the feed's expected clock
(or planned when explicitly on time); unknown delays have null ETA/minutes.
Minutes round up; unknown carriages are null. `next_departure` keeps its TBC
platform convention; unknown `services` platforms are null. Dates and
London offsets handle midnight. Errors use the board API's safe codes/statuses.

Requests share the existing per-route/offset cache and coalescing. A small cached
scan (configured RAIL_CACHE_TTL, default 30 seconds) also avoids another upstream
walk while fresh, across n values and minute boundaries. Rows and ETA countdowns
are projected again locally, so walking/fast setting changes apply immediately. The adapter
walks ten-row feed responses to cover two hours; no extra per-train requests.
`complete: false` means a saturated minute, unavailable board or bounded scan
could not prove coverage. Counts then describe only observed services; the HA
examples deliberately mark that response unavailable. Scans stop after 16 pages
or a 20-second work budget (an in-flight 15-second network timeout may overrun it).
There is no unconditional completeness guarantee for a changing, row-limited feed.

## REST sensor

Merge snippets into your existing YAML sections; do not create duplicate top-level
keys. Change route IDs/entity names as needed. Use the existing trusted LAN address
reachable from HA; no RDM key or ADMIN_TOKEN is needed for reads. Keep the existing
Cloudflare Access protection for remote access. Set Rail's `RAIL_PROVIDER=rail_data`
for live use; the example rejects Demo, stale, incomplete or >3-minute-old data.

```yaml
sensor:
  - platform: rest
    name: Rail Out
    unique_id: rail_out
    resource: "http://minisforum.lan:8098/api/summary?route=out&n=7"
    scan_interval: 60
    timeout: 40
    value_template: >-
      {{ value_json.next_departure.status if value_json.next_departure else 'no_departures' }}
    availability: >-
      {{ not value_json.demo and not value_json.stale and value_json.complete
         and as_timestamp(now()) - as_timestamp(value_json.generated_at, 0) < 180 }}
    json_attributes:
      - next_departure
      - walking_minutes
      - cancelled_count
      - delayed_count
      - services
      - generated_at
      - demo
      - stale
      - complete
```

For the return, duplicate this sensor with name `Rail Back`, unique_id `rail_back`
and `route=back`. Confirm the generated entity IDs in HA before using them below.
A sensor remains available with `no_departures` when all services are cancelled,
so the cancellation automation can still run.

## Time to leave (departure ETA minus walking time)

```yaml
template:
  - sensor:
      - name: Rail time to leave
        unique_id: rail_out_time_to_leave
        device_class: timestamp
        availability: >-
          {% set train = state_attr('sensor.rail_out', 'next_departure') %}
          {{ states('sensor.rail_out') not in ['unknown', 'unavailable']
             and train is not none and train.expected is not none }}
        state: >-
          {% set train = state_attr('sensor.rail_out', 'next_departure') %}
          {% if train is not none and train.expected is not none %}
            {{ (as_datetime(train.expected) - timedelta(
                 minutes=state_attr('sensor.rail_out', 'walking_minutes') | int(0))).isoformat() }}
          {% else %}
            {{ none }}
          {% endif %}
```

This timestamp can already be in the past after a delay update/late refresh;
HA shows it in HA's configured timezone. Unknown ETA makes it unavailable.

## Notify for a chosen train

Create this helper, then copy the desired `id` from the REST sensor's `services`
attribute (Developer Tools → States) into it. Choose a particular service ID,
not just HH:MM, so a different day's train does not match. Clear it after travelling;
IDs are provider-issued and not a recurring timetable subscription. Only the first
n walk-eligible services are returned, so choose a train currently in that list.

```yaml
input_text:
  rail_chosen_service:
    name: Rail chosen service ID
    max: 255

automation:
  - id: rail_chosen_train_cancelled
    alias: Rail chosen train cancelled
    triggers:
      - trigger: template
        value_template: >-
          {% set chosen = states('input_text.rail_chosen_service') %}
          {{ states('sensor.rail_out') not in ['unknown', 'unavailable']
             and chosen not in ['', 'unknown', 'unavailable']
             and (state_attr('sensor.rail_out', 'services') or [])
                 | selectattr('id', 'eq', chosen)
                 | selectattr('status', 'in', ['cancelled', 'part_cancelled'])
                 | list | count > 0 }}
    actions:
      - action: notify.mobile_app_your_iphone
        data:
          title: Train cancelled
          message: "Your selected train no longer serves this journey. Open Rail to choose another."
    mode: single
```

Replace the notification action with your actual notify service. For the return,
use `sensor.rail_back`. The trigger fires when the selected service is observed
cancelled (also immediately if selected after cancellation). Disappearing from
the feed is **not** inferred to mean cancellation. Polling can miss a short-lived
update or one after scheduled departure; this is a convenience alert, not a guarantee.

Check HA configuration and reload/restart as appropriate after adding snippets.
The 60-second sensor polls continuously even with the Rail browser closed: for P
uncached feed pages per poll, budget up to `40,320 × P` calls per route per four
weeks, before shared-cache savings. Monitor RDM usage; duplicate template sensors
above make no additional HTTP requests.
