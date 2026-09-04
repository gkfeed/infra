# AGENTS.md

## Repository purpose

This repository is the sole owner of the shared gkfeed PostgreSQL schema,
versioned SQL migrations, application privileges, and contract documentation.
Applications consume this contract but do not execute DDL.

## Working with tasks

- Tasks live in `.tasks/<timestamp>/TASK.md` and are completed in timestamp
  directory order.
- Before starting a task, check its `DEPENDS` field and complete every listed
  dependency.
- Keep each task small enough for one self-contained PR.
- Work only within the selected task and its definition of done.
- Before each task, read this file and the current contracts of neighboring
  applications.
- Do not change parser or API code from this repository. Inspect them read-only
  when a task requires it.

## Migration and schema rules

- Read `docs/migrations.md` before authoring, reviewing, or applying a
  migration.
- Use plain PostgreSQL SQL compatible with the pinned dbmate version.
- Create migrations only with
  `make new NAME=<lowercase_snake_case_description>`; the generated 14-digit
  timestamp is the permanent migration ID and order.
- Use only this repository's pinned dbmate through its `make` targets. Always
  run dbmate with `--strict`.
- `public.schema_migrations` is the authoritative migration registry. Never
  edit it manually.
- Migrations are forward-only. Once a migration is committed or applied in any
  environment, never rename, reorder, delete, or edit it; add every fix as a
  new migration.
- Use expand-migrate-contract for incompatible changes. Keep the old contract
  until all consumers have moved and the explicit compatibility period is
  complete.
- After testing a migration with `make migrate` and `make status`, update
  `db/schema.sql` with `make dump` in the same PR.
- A designated operator applies merged migrations manually from this
  repository. Applications and application deployments must never run
  migrations or other DDL.
- Do not commit passwords, LOGIN roles, real connection strings, `.env`, or
  other secrets.

## Legacy import

The one-time SQLite importer is a temporary cutover exception. Keep it isolated
from the permanent PostgreSQL contract and remove it in a separate final task
after the cutover is confirmed. Preserve the SQL migration history.
