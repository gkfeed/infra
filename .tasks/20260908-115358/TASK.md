# I11C: Skip valid tombstoned items before PostgreSQL insertion

- STATUS: DONE
- PRIORITY: 1
- DEPENDS: [I11B](../20260907-145623/TASK.md)

## Problem

The importer currently inserts every non-orphan SQLite item and then deletes
items covered by valid tombstones. On the production-sized rehearsal snapshot,
this inserted 89,076 source items before removing 2,623 orphan items and 84,109
distinct valid tombstoned items. PostgreSQL retained about 5.16 GiB of physical
TOAST storage after autovacuum even though the 2,344 surviving items contained
about 556 MiB of text.

The retained pages are reusable inside PostgreSQL but still consume filesystem
space. They also increase WAL and make database-copying contract tests exceed
an 8 GiB rehearsal volume.

## Goal

Keep valid tombstoned items out of PostgreSQL entirely while preserving the
existing import report, reconciliation rules, and transaction guarantees.

## Plan

- [x] Compute the distinct IDs of valid tombstoned items from the same
      read-only SQLite transaction used to build the import plan.
- [x] Exclude those IDs while copying `item` rows instead of inserting and
      deleting them in PostgreSQL.
- [x] Preserve the meanings of `tombstones.valid`, `tombstones.missing`,
      `tombstones.ownership_mismatched`, and `deleted_distinct_items`, including
      duplicate tombstone rows.
- [x] Replace the insert-then-delete target check with a PostgreSQL-side check
      proving that no valid tombstoned item reached the target.
- [x] Preserve orphan removal, feed-ID remapping, target row reconciliation,
      identity-sequence synchronization, rollback behavior, and report shape.
- [x] Add tests covering duplicate valid tombstones, missing tombstones,
      ownership mismatches, orphan items, and an excluded item with large TOAST
      content.
- [x] Update the temporary importer documentation to describe the pre-insert
      exclusion and its target-side verification.
- [x] Do not add `VACUUM FULL`, application DDL, a schema migration, or a
      permanent staging table.

## Validation

- [x] Run all importer tests against disposable PostgreSQL 17 with
      `IMPORT_TEST_DATABASE_URL` set and run the orphan-analysis tests.
- [x] Repeat dry-run and execute against the production-sized rehearsal
      snapshot, then pass the documented report gates and diffs.
- [x] Force a checkpoint and record aggregate `pg_database_size`, `item` heap,
      index, TOAST, WAL, and `PGDATA` sizes without committing private reports.
- [x] Confirm the source SQLite checksum is unchanged and a repeated execute is
      rejected.
- [x] Run the API `/api/v1/list` and `/api/v1/get_items?limit=2` smoke checks
      through `gkfeed_api`, and run the parser schema check through
      `gkfeed_parser`.

All 17 importer tests passed against a disposable PostgreSQL 17 database, and
both orphan-analysis tests passed. The fault-injection case forced a valid
tombstoned item through the copy transform; the PostgreSQL exclusion check
rejected it and the transaction rolled back.

The production-sized dry-run and execute reports passed the documented gates
and diffs. Execute retained 2,344 items and reported 84,109 distinct valid
tombstoned items. After a checkpoint, `pg_database_size` was 638,225,555 bytes.
The item heap was 532,480 bytes, its indexes were 73,728 bytes, and its TOAST
relation was 601,915,392 bytes. WAL occupied 671,100,928 bytes and complete
`PGDATA` occupied 1,325,100,334 bytes. No private report was retained.

The source SQLite checksum was unchanged and a repeated execute failed the
empty-target guard. The parser schema check passed through a LOGIN role with
only `gkfeed_parser` membership. API commit `f6520e6` returned HTTP 200 with
valid JSON for `/api/v1/list` and `/api/v1/get_items?limit=2` through a LOGIN
role with only `gkfeed_api` membership.

## Definition of done

The importer never writes a valid tombstoned item to PostgreSQL, all existing
reconciliation and safety checks still pass, and the known production-sized
snapshot produces the same 2,344 target items. After a forced checkpoint, the
`item` relation occupies less than 1 GiB and complete `PGDATA` occupies less
than 3 GiB. The optimization requires no post-import table rewrite and no
change to the permanent PostgreSQL contract.
