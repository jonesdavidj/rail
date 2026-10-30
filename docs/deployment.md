# Deployment

Use root compose.yaml with Portainer stack variables from .env.example. The merged
Dockerfile listens on 8097; Compose publishes host 8097 to container 8097. Keep the
local rail-data volume at /data, /tmp tmpfs, non-root UID/GID 10001, explicit
linux/amd64 platform, restart unless-stopped and TZ=Europe/London. No NAS or edge
network dependency, TLS listener or application login.

The merged main workflow runs Ruff/pytest on PRs and publishes Docker Hub main
and sha-<7-character-commit> tags after successful main pushes. Configure Actions
secrets DOCKERHUB_USERNAME and DOCKERHUB_TOKEN. Set DOCKERHUB_USERNAME and
RAIL_IMAGE_TAG in Portainer. Prefer an immutable SHA tag for deliberate rollout:
Watchtower can advance containers following main. No Portainer webhook is added.

Compose defaults to Demo, including after upgrading this branch. Configure the
RDM key/Specification URL in Portainer, run the one-request --check CLI, then set
RAIL_PROVIDER=auto or rail_data to enable live boards. Never put the key in chat or
Git. See README for complete setup. No production deployment is performed here.

## Operations and releases

See the [runbook](runbook.md) for Portainer deployment/rollback, key rotation,
feed failures and volume backup. The manual Release workflow promotes an already
published main SHA image to an immutable `vX.Y.Z` tag and adds the matching Git tag.
It does not deploy or move the `main` image tag.

## Docker repo README snippet

Suggested additional row for `jonesdavidj/docker`'s existing `Layer | Stacks` table;
this is documentation to copy there, not a stack owned by that repo:

```markdown
| App in its own repo | Rail — deployed by Portainer from [jonesdavidj/rail](https://github.com/jonesdavidj/rail), using its `compose.yaml`; image `jonesdavidj/rail`, host port 8097, local volume `rail-data` |
```
