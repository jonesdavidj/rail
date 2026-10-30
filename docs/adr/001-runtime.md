# ADR 001: One Python service and a provider boundary

Status: accepted for phase 1; live-provider stub superseded by ADR 004.

Use FastAPI, Pydantic and one Uvicorn worker, matching existing app repos. Serve
minimal static assets from the same process. Keep raw feed parsing outside HTTP
handlers and behind an injected provider protocol; inject a clock for offline tests.

Demo implements the protocol now. RailDataProvider implements the same method but
raises a typed unavailable error until phase 2. Explicit live selection must never
fall back to synthetic trains. No credentials or network client are needed yet.

A small frontend framework and a separate proxy container would add maintenance
without helping this phase. Final UI and memory caching remain future work.
