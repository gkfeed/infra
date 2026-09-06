# I07 — Import confirmed tables

- STATUS: DONE
- PRIORITY: 1
- DEPENDS: [I03](../20260904-0903/TASK.md), [I06A](../20260904-090650/TASK.md)

## Prerequisite

The I03 contract matrix is fully confirmed.

## Goal

Implement migration of confirmed tables only from SQLite to PostgreSQL.

## Plan

- [x] Transfer confirmed tables in foreign-key order in one controlled
      operation.
- [x] Create a transaction-local PostgreSQL staging table for legacy SQLite
      `deleted_items` and load tombstones into it after the domain rows exist.
- [x] Validate every staged tombstone against item, feed, and user ownership;
      physically delete only matching imported items.
- [x] Report counts for deleted items and ignored missing or ownership-mismatched
      tombstones without exposing row contents.
- [x] Remove the staging table before cutover. It must be dropped on commit and
      leave no permanent PostgreSQL contract.
- [x] Preserve explicit IDs.
- [x] Convert any remaining plaintext SQLite passwords to the target password
      hash before insertion; never write or log plaintext in PostgreSQL.
- [x] Treat naive timestamps as UTC.
- [x] Preserve aware timestamps as the same instant.
- [x] Do not transfer legacy `itemhash`.
- [x] Take API-table policies only from the confirmed API contract.
- [x] Reject repeated runs against a non-empty target.
- [x] Ensure an error leaves the target clean or explicitly fit only for
      recreation.

## Definition of done

A repeated run against a non-empty target is rejected, failure consequences are
unambiguous, transferred table counts match, valid tombstones remove the
corresponding PostgreSQL items, and no staging objects remain after success.

## Validation

Fourteen importer tests passed against disposable PostgreSQL 17, including
read-only dry-run, explicit execute, injected failure rollback, parser-state
normalization, password conversion, tombstone ownership, repeated-run rejection,
and cleanup of transaction-local staging. Two tests for the private orphan-item
analysis tool also passed.

A restored production rehearsal snapshot passed SQLite `integrity_check`,
dry-run, transfer, aggregate reconciliation, and repeated-run rejection. The
3,963,270,505-byte source archive passed gzip CRC verification and had SHA-256
`a0ea68894db04c3f50f19a4005bbbc7d9eb2ae012cd6112edcbcfa0fe51d54ea`. The
committed disposable target contained 5 users, 1,348 feeds, 2,344 items, 1,347
feed-parser rows, and 106,384 item hashes. Normalization removed 34 duplicate
feeds, 2,623 orphan items, 50 orphan feed-parser rows, 4,376 orphan item hashes,
and 2,061 item-hash merge collisions. Valid tombstones deleted 84,109 distinct
items; 2,417 missing tombstones deleted nothing; no ownership mismatch occurred.
No permanent staging table or orphan target references remained. No production
record contents or credentials were retained in the repository.

Pinned dbmate 2.35.1 applied both existing migrations in strict mode, and
`make status` reported two applied migrations with none pending. I08 remains
responsible for integer range checks and identity-sequence synchronization.
