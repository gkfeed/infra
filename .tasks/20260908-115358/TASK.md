# I11C: Skip valid tombstoned items before PostgreSQL insertion

- STATUS: PENDING
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

- [ ] Compute the distinct IDs of valid tombstoned items from the same
      read-only SQLite transaction used to build the import plan.
- [ ] Exclude those IDs while copying `item` rows instead of inserting and
      deleting them in PostgreSQL.
- [ ] Preserve the meanings of `tombstones.valid`, `tombstones.missing`,
      `tombstones.ownership_mismatched`, and `deleted_distinct_items`, including
      duplicate tombstone rows.
- [ ] Replace the insert-then-delete target check with a PostgreSQL-side check
      proving that no valid tombstoned item reached the target.
- [ ] Preserve orphan removal, feed-ID remapping, target row reconciliation,
      identity-sequence synchronization, rollback behavior, and report shape.
- [ ] Add tests covering duplicate valid tombstones, missing tombstones,
      ownership mismatches, orphan items, and an excluded item with large TOAST
      content.
- [ ] Update the temporary importer documentation to describe the pre-insert
      exclusion and its target-side verification.
- [ ] Do not add `VACUUM FULL`, application DDL, a schema migration, or a
      permanent staging table.

## Validation

- [ ] Run all importer tests against disposable PostgreSQL 17 with
      `IMPORT_TEST_DATABASE_URL` set and run the orphan-analysis tests.
- [ ] Repeat dry-run and execute against the production-sized rehearsal
      snapshot, then pass the documented report gates and diffs.
- [ ] Force a checkpoint and record aggregate `pg_database_size`, `item` heap,
      index, TOAST, WAL, and `PGDATA` sizes without committing private reports.
- [ ] Confirm the source SQLite checksum is unchanged and a repeated execute is
      rejected.
- [ ] Run the API `/api/v1/list` and `/api/v1/get_items?limit=2` smoke checks
      through `gkfeed_api`, and run the parser schema check through
      `gkfeed_parser`.

## Definition of done

The importer never writes a valid tombstoned item to PostgreSQL, all existing
reconciliation and safety checks still pass, and the known production-sized
snapshot produces the same 2,344 target items. After a forced checkpoint, the
`item` relation occupies less than 1 GiB and complete `PGDATA` occupies less
than 3 GiB. The optimization requires no post-import table rewrite and no
change to the permanent PostgreSQL contract.
