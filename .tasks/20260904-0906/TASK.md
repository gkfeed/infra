# I06 — Add the temporary importer skeleton

- STATUS: DONE
- PRIORITY: 1
- DEPENDS: [I04](../20260904-0904/TASK.md)

## Goal

Create a safe dry-run skeleton for the temporary SQLite-to-PostgreSQL importer,
without transferring data yet.

## Plan

- [x] Create an isolated Python CLI in `legacy-import/` with separate
      dependencies.
- [x] Accept paths and URLs only through command-line arguments or environment
      variables.
- [x] Open SQLite read-only.
- [x] Connect to PostgreSQL and refuse to run if target domain tables are not
      empty.
- [x] In dry-run mode, print only safe counts and a schema summary.
- [x] Count legacy `deleted_items` tombstones and classify valid, missing, and
      ownership-mismatched rows without printing their contents.
- [x] Count plaintext and already-hashed password rows without printing either
      representation.
- [x] Design the tombstone staging table as transaction-local PostgreSQL state;
      it must never become part of the canonical `public` schema.
- [x] Never print credentials or record contents.
- [x] Do not transfer data in this task.

## Definition of done

Dry-run safely shows counts and a schema summary without exposing credentials
or record contents.

## Validation

Five unittest checks passed, including integration against disposable PostgreSQL
17 provisioned through pinned dbmate with `make migrate` and `make status`.
`make dump` showed no schema changes apart from the server version comment,
which was kept unchanged. Checks cover aggregate tombstone and password counts,
redaction, missing source schema, SQLite read-only access and missing-file
handling, PostgreSQL read-only enforcement, and non-empty target rejection.
See `legacy-import/README.md` for usage and the transaction-local staging design.
Password representation counts are preliminary; I06A owns strict validation.
