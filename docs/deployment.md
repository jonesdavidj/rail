# Deployment

Use root compose.yaml with Portainer stack variables from .env.example. The merged
Dockerfile listens on 8097; Compose publishes host 8098 to container 8097. Keep the
local rail-data volume at /data, /tmp tmpfs, non-root UID/GID 10001, explicit
linux/amd64 platform, restart unless-stopped and TZ=Europe/London. No NAS, edge
network attachment, TLS listener or application login. The external rail_ingress
network must exist before deploying; it is owned by the Docker repo edge stack.
Shared Caddy uses rail-origin:8097; direct LAN clients use minisforum.lan:8098.
Portainer variables override defaults: remove RAIL_HOST_PORT=8097 or set it to
8098 before Pull and redeploy. Keep the existing stack project and rail-data volume.

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
| App in its own repo | Rail — deployed by Portainer from [jonesdavidj/rail](https://github.com/jonesdavidj/rail), using its `compose.yaml`; image `jonesdavidj/rail`, host port 8098, local volume `rail-data` |
```


## Explicit bridge subnet repair

Shared ingress uses the Docker repo networking/bootstrap_networks.py and allocation.json; private backends have explicit /24 IPAM. Preserve existing stack projects, volume identities and published ports during network recreation. Follow the [ordered migration and rollback](https://github.com/jonesdavidj/home-infrastructure/blob/main/network/docker-subnet-migration.md) before deploying over old subnets. Runtime checks remain pending deployment.
