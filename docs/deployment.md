# Deployment

## Registry default: GHCR

Default image naming in this template uses GHCR:

- `ghcr.io/<owner>/<repo>:latest`
- `ghcr.io/<owner>/<repo>:<git-sha>`

### Switch to Docker Hub

1. Change image references in:
   - `compose/docker-compose.yml`
   - `compose/docker-compose.portainer.yml`
   - `.github/workflows/ci.yml` (`REGISTRY` and login step)
2. Add Docker Hub credentials as GitHub Actions secrets.

## Portainer stack deployment from GitHub

Use `compose/docker-compose.portainer.yml` in Portainer stack settings.

Recommended env vars in Portainer:

- `IMAGE_NAME`
- `APP_ENV`
- `APP_PORT`
