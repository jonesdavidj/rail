# Operations

See [README](../README.md). /api/health remains HTTP 200 when defaults are served;
check config_source, config_warning, provider_ready and degraded for diagnostics.
The Docker healthcheck tests local responsiveness without contacting a provider.
Logs are JSON on stdout. No config writes or external requests occur in phase 1.
Back up only /data/routes.json; restart after editing it. Keep readable permissions
for UID/GID 10001. Restoring a broken config still permits default-route startup.
Rollback uses a previous immutable image with a compatible config version.

In the managed development environment, Docker builds may need the session CA:
`docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t rail:local .`.
The Dockerfile's optional BuildKit secret supplies pip trust only for that step;
the session CA is never copied into image layers. Normal GitHub builds need no secret.
