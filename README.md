# gkfeed infra

This repository owns the shared gkfeed PostgreSQL contract: dbmate migrations,
the current schema dump, application roles, and contract documentation.
Applications consume this contract but do not execute DDL.

## Requirements

- GNU Make;
- Docker with host-network access to PostgreSQL.

The dbmate version is pinned in `Makefile`; no local dbmate installation is
needed. List the available commands:

```sh
make help
```

Database commands read `DATABASE_URL` from either the environment or a local
`.env` file:

```sh
DATABASE_URL='postgres://user:password@127.0.0.1:5432/gkfeed?sslmode=disable' make status
```

Alternatively, create an untracked `.env` file:

```dotenv
DATABASE_URL=postgres://user:password@127.0.0.1:5432/gkfeed?sslmode=disable
```

Then run commands without repeating the URL:

```sh
make status
make migrate
make dump
```

Create a timestamped migration:

```sh
make new NAME=add_example
```

Every dbmate invocation enables strict mode. Migrations live in
`db/migrations/`, and the current dump is written to `db/schema.sql`. Do not
commit connection strings, passwords, or `.env` files.

Before authoring or applying a migration, read the
[migration policy](docs/migrations.md). It defines migration naming and
ordering, the forward-only workflow, manual execution, the
`public.schema_migrations` registry, and expand-contract changes.

See [application roles](docs/application-roles.md) for the grants, operator
requirements, and executable privilege smoke checks.

Follow [the manual cutover runbook](docs/manual-cutover.md) for the one-time
production transfer.

The temporary [SQLite importer](legacy-import/README.md) supports read-only
inspection and the controlled one-time transfer into an empty PostgreSQL
target.
