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

## Boundaries

- Infra migrations contain schema and privilege changes, not application code.
- Required backfills must be explicit, bounded, and reviewed. Routine data
  changes do not belong in migrations.
- Keep the temporary SQLite importer separate from PostgreSQL migration
  history.
