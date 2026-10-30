# Deployment

See the [README](../README.md#container-and-deployment) for the single root
compose.yaml, Portainer variables, host port 8097 and named local rail-data volume.
The scaffold's GHCR publishing and duplicate Compose files have been removed.
Phase 1 CI builds and tests only. Do not deploy externally before Cloudflare
Access protects the hostname. TLS and hostname routing belong to the existing
shared Caddy/proxy repository. No production deployment is performed in phase 1.
