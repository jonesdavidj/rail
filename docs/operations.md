# Operations

/api/health is local health (HTTP 200 while serving), not a live subscription
probe. Inspect provider_ready, config_source, config_warning and degraded. Use
`python -m app --check --raw` for deliberate live checks when a key is available.

Settings/key-file changes and manual route-file edits require restart. API route
writes persist immediately and atomically. Back up /data/routes.json, preserve
readability for UID/GID 10001 and restore only compatible config versions. Empty
or unreadable volumes still serve defaults; startup never replaces broken data.

Inspect board stale/error/cache_age_seconds for feed issues. Stale lifetime is
900 seconds from the last good fetch; failures never renew it. In-memory cache
and cooldowns reset on restart. Run one Uvicorn worker and use the documented
[quota budget](api-budget.md). No background polling or persistent departure data.

Remote access requires Cloudflare Access; optional ADMIN_TOKEN restricts writes
further. Do not expose 8097 publicly. Use a previous immutable image for rollback.
Do not put keys, raw CLI diagnostic output or runtime data in Git.

In the managed environment Docker builds may need the session CA:
`docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t rail:local .`.
The optional BuildKit secret supplies pip trust only for that step and is not
copied into image layers. Standard GitHub builds need no such secret.
