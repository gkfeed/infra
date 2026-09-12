# I16: Keep production migrations from modifying the schema dump

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: none

## Problem

The `make migrate` target lets dbmate dump `db/schema.sql` automatically after
applying a migration. The generated PostgreSQL version comment includes server
build metadata. Applying migration `20260911093048` on production therefore
changed the tracked file from `17.10` to `17.10 (Debian
17.10-1.pgdg12+1)`, even though the database schema did not change.

This leaves the production checkout dirty and can block a later fast-forward
deployment. A production migration must not rewrite repository files.

## Goal

Make migration application read-only with respect to the repository checkout.
Keep `db/schema.sql` generation an explicit development and release step through
`make dump`.

## Plan

- [ ] Run dbmate migrations with `--no-dump-schema` in `make migrate`.
- [ ] Keep `make dump` as the only Make target that writes `db/schema.sql`.
- [ ] Update migration documentation to distinguish applying migrations from
      refreshing the committed schema dump.
- [ ] Add a regression check proving that `make migrate` leaves tracked files
      unchanged both with pending migrations and when the database is current.
- [ ] Verify that `make dump` still produces the expected schema artifact for a
      migration change before it is committed.

## Definition of done

An operator can run `make migrate` against production without changing any
tracked file. Developers still refresh and review `db/schema.sql` explicitly
with `make dump` in the same change as a migration.

## Validation

Using the pinned dbmate image and a disposable PostgreSQL 17 database, record
clean `git status --short` output before and after `make migrate` with a pending
migration, repeat it with no pending migrations, and confirm that `make dump`
remains the explicit command that updates `db/schema.sql`.
