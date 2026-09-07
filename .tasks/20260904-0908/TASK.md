# I08 — Synchronize sequences and validate INTEGER ranges

- STATUS: DONE
- PRIORITY: 1
- DEPENDS: [I07](../20260904-0907/TASK.md)

## Goal

Protect the import from ID overflow and synchronize PostgreSQL sequences after
preserving explicit IDs.

## Plan

- [x] Before writing, verify that every imported ID fits in PostgreSQL
      `INTEGER`.
- [x] On overflow, stop the import before changing the target.
- [x] After import, set each identity or sequence relative to `MAX(id)`.
- [x] Verify the next generated ID with a safe insert in a rolled-back
      transaction.
- [x] Do not add a full data-checksum system.

## Definition of done

The next generated ID does not conflict with imported IDs, and range overflow
stops the import before target changes.

## Validation

All 17 importer tests passed against disposable PostgreSQL 17. Checks cover
integer columns in every imported table and tombstone staging, overflow rejection
before copy operations with unchanged target rows and sequences, empty tables,
negative and zero IDs, sparse IDs, and generation of the final available INTEGER
ID. Sequence probes leave no rows and restore their consumed IDs. Rolling back
the outer transaction restores the original sequence states.

Pinned dbmate 2.35.1 passed `make migrate`, `make status`, and `make dump` in
strict mode. Both existing migrations are applied with none pending. The dump
only changed the server-version comment, which was kept unchanged. No migration
or application changes were needed.
