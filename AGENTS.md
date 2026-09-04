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

- Use plain PostgreSQL SQL compatible with the pinned dbmate version.
- Always run dbmate with `--strict`.
- Migrations are forward-only.
- Never edit an applied migration; add every fix as a new migration.
- Use expand-contract for incompatible changes.
- Do not add DDL to applications.
- Do not commit passwords, LOGIN roles, real connection strings, `.env`, or
  other secrets.

## Legacy import

The one-time SQLite importer is a temporary cutover exception. Keep it isolated
from the permanent PostgreSQL contract and remove it in a separate final task
after the cutover is confirmed. Preserve the SQL migration history.
