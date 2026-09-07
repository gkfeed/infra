# Migration policy

This repository owns the gkfeed PostgreSQL schema. Applications consume it but
must not run migrations or other DDL.

## Create a migration

```sh
make new NAME=<lowercase_snake_case_description>
```

- Migrations live in `db/migrations/`.
- The generated `<YYYYMMDDHHMMSS>_<name>.sql` timestamp is its permanent ID and
  order. Do not set or edit it by hand.
- If two branches produce the same timestamp, regenerate one before applying
  either migration.
- Use plain PostgreSQL SQL in the `migrate:up` section. Leave `migrate:down`
  empty or omit it.
- Use only this repository's pinned dbmate through `make`; strict mode is
  mandatory.

## Forward-only history

- `public.schema_migrations` is the authoritative registry. Never edit it
  manually.
- Once a migration is committed or applied, never rename, reorder, delete, or
  edit it. Add a later migration for every correction.
- Rollbacks also use a new forward migration; deployments never run DDL
  backward.

## Validate and apply

Test locally or against disposable PostgreSQL:

```sh
make status
make migrate
make status
make dump
```

- Include the updated `db/schema.sql` in the migration PR.
- Complete the migration compatibility section from
  `.github/PULL_REQUEST_TEMPLATE/migration.md` in the PR description.
- Review compatibility, locks, backfill cost, and grants.
- Use dbmate's default transaction. Any exception must be explicit and
  reviewed.
- Do not apply unmerged migrations to shared environments.

A designated operator manually applies merged migrations:

```sh
DATABASE_URL='<operator connection URL>' make status
DATABASE_URL='<operator connection URL>' make migrate
DATABASE_URL='<operator connection URL>' make status
```

Keep credentials, LOGIN roles, real connection URLs, and `.env` files out of
Git.

## Independent application releases

Parser and API releases do not have to happen together. Each application
release must declare the migration ID that first provides the database contract
it needs. At startup, the application checks that
`public.schema_migrations` contains that ID or a later ID. It rejects an older
schema, but it must not require its minimum ID to be the latest applied
migration, compare against an exact migration count, or reject later compatible
migrations. This threshold check relies on strict migration ordering and the
rule that nobody edits the registry by hand.

When a migration expands an application's contract, merge and apply it before
deploying the application release that requires it. Record the new minimum
migration ID in that application and in the migration PR's compatibility
section. An application deployment does not apply the migration.

Later migrations remain compatible through the rules below. A minimum-version
check proves that required schema has been applied. It does not make a contract
migration safe on its own.

## Incompatible changes

Use separate releases and forward migrations:

1. **Expand:** add the compatible replacement without removing the old
   contract.
2. **Migrate:** deploy consumers and backfill data while supporting both
   contracts.
3. **Contract:** remove the old contract only after all consumers have moved
   and the explicit compatibility period has ended.

This applies to incompatible renames, type changes, removals, and new mandatory
values.

A shared column cannot be renamed or removed in one migration. The expand
migration adds its replacement while the old column remains usable. During the
migrate phase, every parser and API version that can run against the database
must work with the expanded schema, and any required backfill must finish. A
later contract migration may remove the old column only when the compatibility
period recorded in the expand PR has ended.

The compatibility period must name:

- the migration ID that starts it;
- every affected application and the first release that no longer needs the
  old contract;
- how mixed old and new application versions behave during deployment;
- the end condition and the evidence that will prove it, including deployment
  of the named application releases and completion of any backfill;
- the earliest date or operational milestone when the contract migration may
  be applied.

The contract migration PR must link that evidence. An elapsed date without
deployment and backfill evidence does not end the period. If the evidence is
missing, keep the old column.

## Boundaries

- Infra migrations contain schema and privilege changes, not application code.
- Required backfills must be explicit, bounded, and reviewed. Routine data
  changes do not belong in migrations.
- Keep the temporary SQLite importer separate from PostgreSQL migration
  history.
