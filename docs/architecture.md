# Architecture

[Runtime](adr/001-runtime.md), [route config](adr/002-route-config.md),
[normalisation/paging](adr/003-normalisation-and-paging.md) and
[live provider/atomic route writes](adr/004-live-provider-and-route-writes.md).
Later ADRs supersede phase-1 stubs/read-only limits.

main.py is the HTTP boundary; config.py validates models/settings; routes.py owns
atomic JSON persistence; providers.py supplies Demo; rail_data.py implements the
RDM client, shared TTL cache and coalescing. normalise.py maps raw data into
models.py; paging.py builds pages; stations.py searches the bundled catalogue.
__main__.py performs deliberate one-request live diagnostics. The minimal static
preview is not a final UI. Runtime config and credentials are never image assets.
