# Rail operations

## Deploy and roll back

1. Merge the PR; wait for main CI to publish `jonesdavidj/rail:sha-<first 7 commit characters>`.
2. In Portainer, use the `rail` Repository stack from `jonesdavidj/rail`, branch
   `main`, path `compose.yaml`. Keep all settings in stack variables, as documented
   in `.env.example`; retain `RAIL_DATA_VOLUME=rail-data` and `/data`.
3. Record the current image tag. Set `DOCKERHUB_USERNAME=jonesdavidj` and
   `RAIL_IMAGE_TAG=sha-<short>` (only the tag, no colon/image prefix). Choose
   `RAIL_PROVIDER=rail_data` for live data and supply the subscribed base URL/key,
   or `demo` for clearly labelled samples. Use **Pull and redeploy**.
4. Check container health, `/api/health` (`provider_ready`, `mode`, `config_warning`)
   and both boards. Health checks local configuration, not upstream availability.
   In Portainer's container console, `python -m app --check` makes one live request;
   use `--route <id>` if the default `out` route was removed.

Roll back: change `RAIL_IMAGE_TAG` to the recorded good SHA or version tag, then
**Pull and redeploy** and repeat the checks. Keep the volume and stack variables.
If Compose itself must roll back, select its known-good Git reference in the
Repository stack as well; changing an image tag alone does not roll back Compose.

Watchtower polls every five minutes. Tracking `main` permits automatic image
updates between deliberate redeploys. Pinning `sha-<short>` or `vX.Y.Z` prevents
advancement to another version; keep these tags immutable and retain old images
in Docker Hub. Do not use `latest`.

For a version release, run Actions → **Release** → **Run workflow** on `main`,
entering e.g. `v1.0.0`, after that commit's main image build succeeds. It promotes
that SHA image to `jonesdavidj/rail:v1.0.0` and creates the matching Git tag, without
moving `main` or deploying. Existing tags may only be reused for the same commit
and image digest. Uses existing `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` Actions
secrets (the token needs push permission); no token belongs in Git. Set Docker
Hub immutable-tag protection for `vX.Y.Z`/SHA tags if available; leave `main` mutable.

## Rotate the Rail Data key

Create a replacement consumer key in RDM. In Portainer replace
`RAIL_DATA_API_KEY` (not the consumer secret), leave `RAIL_DATA_API_KEY_FILE` empty,
and **Pull and redeploy** to reload it. Run the one-request check above and verify
a live board, then revoke the old key. Never put the key in Git or diagnostics.
If using the already configured secret-file alternative, replace that file,
keep it readable by UID 10001, leave the environment key empty and recreate the
container. Only one credential source may be set.

## Feed problems

The board labels stale data for at most 15 minutes from the last successful
fetch, then shows an error. Restarting clears this memory cache. Do not restart
repeatedly or hammer refresh; inspect the board's error and container JSON logs.

| Symptom | Action |
|---|---|
| Rejected key: upstream 401/403 (`authentication`) | Check consumer key whitespace, active subscription and entitlement to this product; rotate if needed. A settings-write 401 instead concerns `ADMIN_TOKEN`. |
| 429 (`rate_limit`) | Wait for `Retry-After`; the server applies a cooldown. Check RDM usage, close redundant boards, increase both `RAIL_REFRESH_SECONDS` and `RAIL_CACHE_TTL` and redeploy. |
| `routing` (400/404/500), or redirect | Verify the complete base URL from the subscribed Specification and its allowed hostname; check station codes and try a default route. Do not follow redirects or broaden the allowlist speculatively; 500 may be an outage. |
| Timeout, connection, bad JSON or upstream outage | Check RDM service status and server connectivity; wait for automatic retries. Escalate persistent invalid responses to RDM. |

For a prolonged outage, leaving the explicit error is safe. If deliberately
switching to `RAIL_PROVIDER=demo`, redeploy and expect labelled samples, never live
trains; restore `rail_data` and redeploy after recovery. Existing ingress stays as configured.

## Change routes

Open the gear beside the clock. Select From/To from station search; optionally add
the return, set walking minutes, edit labels, reorder or remove routes. Supply
the editing token if `ADMIN_TOKEN` is enabled. Changes save immediately for every
device. Each device remembers its own selected tab. Manual `/data/routes.json`
edits require restart; prefer the UI's validation.

## Back up / restore

Run on the Docker host from the directory holding the archive. These commands
use the default volume name; substitute the actual `RAIL_DATA_VOLUME` if changed.
Backup is safe while running (route writes use atomic replacement):

```sh
docker run --rm --mount type=volume,src=rail-data,dst=/data,readonly --mount type=bind,src="$PWD",dst=/backup alpine:3.21 tar -czf /backup/rail-data.tgz -C /data .
```

For restore, stop `rail` in Portainer first, ensure the target volume is empty
(restoring replaces saved routes), then run this one command and start `rail`:

```sh
docker run --rm --mount type=volume,src=rail-data,dst=/data --mount type=bind,src="$PWD",dst=/backup,readonly alpine:3.21 sh -c 'tar -xzf /backup/rail-data.tgz -C /data && chown -R 10001:10001 /data'
```

Verify routes and health. Retain the archive off-host. Recreating the volume loses
only custom routes, including labels/order/walking settings; the two built-in
routes return. API credentials remain Portainer variables and departures were
only cached in memory. Missing/unreadable config also falls back to defaults and
reports a warning in `/api/health`; check restored ownership before saving edits.
