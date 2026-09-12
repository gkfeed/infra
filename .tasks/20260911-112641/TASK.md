# I15: Version production Compose overlays and use them for deploys

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: none

## Problem

The parser and API servers have untracked `docker-compose.production.yml`
overlays. Their deploy targets update `master` and then run plain
`docker compose` commands, so production behavior depends on server-only files
or local `COMPOSE_FILE` state.

This has already produced configuration drift. The API container joined the
external PostgreSQL network, while the parser containers started from only the
base Compose file. The parser could not resolve `postgres`, and its dispatcher
entered a restart loop.

## Goal

Keep each application's production Compose overlay in its own repository and
make every deploy from `master` explicitly use the tracked base and production
files. A fresh checkout plus private environment values must be enough to
recreate the production services.

This is a coordinating task. Implement application Compose and deployment
changes in the parser and API repositories, not in the infra repository.

## Plan

- [ ] Add the current production overlay to the parser repository as tracked
      `docker-compose.production.yml`.
- [ ] Preserve the parser production requirements in that overlay: attach
      dispatcher and both workers to the external `gkfeed-infra_default`
      network, and select the production Chromium image where required.
- [ ] Add the current production overlay to the API repository as tracked
      `docker-compose.production.yml` and attach the app to the same external
      PostgreSQL network.
- [ ] Keep passwords, connection URLs, tokens, and other environment-specific
      values in ignored server environment files. Do not put them in either
      Compose file.
- [ ] Define one production Compose command in each Makefile with both files
      listed explicitly, for example `docker compose -f docker-compose.yml -f
      docker-compose.production.yml`.
- [ ] Use that same command for config validation, stop/remove operations,
      builds, recreation, worker-only recreation, and status checks. Do not
      depend on a server-local `COMPOSE_FILE` value.
- [ ] Make the GitHub Actions deploy job triggered by a push to `master` call
      the production target after a fast-forward-only update.
- [ ] Validate the merged Compose configuration in CI with production-safe
      placeholder values before allowing deployment.
- [ ] After the first successful tracked deployment, verify through Docker
      Compose labels that both config files were used and that API and parser
      services share `gkfeed-infra_default` with PostgreSQL.
- [ ] Confirm that parser resolves `postgres`, dispatcher remains running, and
      the API and parser PostgreSQL smoke checks required by I13 pass.
- [ ] Remove reliance on the old ignored server-only overlays after the tracked
      deployment is verified.

## Definition of done

A push to `master` in either application repository recreates its production
containers from the tracked base and production Compose files. No production
topology exists only on the server. API and parser connect to the PostgreSQL
service through `gkfeed-infra_default`, and the final I13 application smoke
checks pass.

## Validation

Record the merged `docker compose config` checks, the deployed Compose config
file labels, shared-network membership, stable container status, and the API
and parser smoke-check results. Do not record secrets or real connection URLs.
