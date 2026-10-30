# ADR 002: Runtime JSON routes and bundled stations

Status: accepted for phase 1.

Routes are validated data in /data/routes.json, not Python branches. Built-in
fallback routes are created only when configuration cannot be loaded. Do not
write fallback data over the missing or unreadable file. Report categories in
health without echoing private configuration or validation payloads to logs.

One JSON document with a version and ordered routes is sufficient. Load once;
restart to reload in phase 1. Route editing/atomic persistence is outside this
read-only API scope. An empty list is valid. Bound route/file sizes and validate
all fields strictly against the bundled CRS catalogue.

Use a local Docker named volume rail-data; NAS availability must not affect startup.
Bundle a derived Trainline GB station catalogue under ODbL, with provenance,
transformation and full licence shipped in the image. It replaces the tentative
NaPTAN choice because accessible source/terms were verified for this snapshot.
Do not infer live feed coverage from station membership.
