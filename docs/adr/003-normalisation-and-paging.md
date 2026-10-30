# ADR 003: Provisional feed normalisation and prototype paging

Status: original paging decision superseded by the correction below; live contract verification pending.

Port the prototype's expected/planned timing, reasons, destination truncation,
midnight rollover, seven-row default and time-offset Earlier/Later behaviour.
Use public-model field casing (notably serviceID and nrccMessages[].Value).
The official schema could not be verified during planning; this adapter is not
an approved live-feed contract. Verify the current public contract in phase 2.

Intentional corrections to prototype fixtures:
- Preserve replacement buses with service_type=bus because phase 1 requests them.
- Select a usable calling-point group containing the selected destination.
- Do not infer a departure formation from a later calling point.
- Unknown estimates stay unknown rather than automatically becoming delayed.
- Actual departure atd is not assumed in the public detailed-board model.
- Feed generation time is retained where supplied and timezone-aware.
- Reject malformed/unknown API parameters instead of clamping them silently.

Walking time filters scheduled departures on current/future pages; Earlier
intentionally shows the historical window. Next uses the prototype minute cursor,
including its known same-minute boundary limitation. Offset bounds -60..119 and
120-minute windows are Demo/prototype policy, not verified provider constraints.
Full snapshot paging would change requested semantics and is deferred.

HH:MM dates are inferred within the bounded window relative to an aware London
clock. During the autumn repeated hour, date-less feed fields cannot unambiguously
identify which occurrence is meant. Do not claim this heuristic solves that feed
limitation; validate available metadata before enabling live service.

## Paging correction — 2026-10-30

The no-skips/repeats acceptance check reproduced failures with same-minute trains
and advancing clocks. Replace the prototype's minute-plus-one cursor with a
stateless, validated absolute time/service-ID boundary and an anchored two-hour
horizon. Re-fetch its minute inclusively, discard rows at/before the boundary,
and recompute the upstream offset on every request. This is still a live feed,
not persisted departure snapshots. Full ten-row responses permit another fetch;
only known excess rows or an unsaturated feed establish an end. Cursors expire
after 15 minutes and require the same route pair. No runtime persistence changes.
See [observed defects and remaining live checks](../live-validation.md).
