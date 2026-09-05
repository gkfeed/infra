# I07 — Import confirmed tables

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [I03](../20260904-0903/TASK.md), [I06A](../20260904-090650/TASK.md)

## Prerequisite

The I03 contract matrix is fully confirmed.

## Goal

Implement migration of confirmed tables only from SQLite to PostgreSQL.

## Plan

- [ ] Transfer confirmed tables in foreign-key order in one controlled
      operation.
- [ ] Create a transaction-local PostgreSQL staging table for legacy SQLite
      `deleted_items` and load tombstones into it after the domain rows exist.
- [ ] Validate every staged tombstone against item, feed, and user ownership;
      physically delete only matching imported items.
- [ ] Report counts for deleted items and ignored missing or ownership-mismatched
      tombstones without exposing row contents.
- [ ] Remove the staging table before cutover. It must be dropped on commit and
      leave no permanent PostgreSQL contract.
- [ ] Preserve explicit IDs.
- [ ] Convert any remaining plaintext SQLite passwords to the target password
      hash before insertion; never write or log plaintext in PostgreSQL.
- [ ] Treat naive timestamps as UTC.
- [ ] Preserve aware timestamps as the same instant.
- [ ] Do not transfer legacy `itemhash`.
- [ ] Take API-table policies only from the confirmed API contract.
- [ ] Reject repeated runs against a non-empty target.
- [ ] Ensure an error leaves the target clean or explicitly fit only for
      recreation.

## Definition of done

A repeated run against a non-empty target is rejected, failure consequences are
unambiguous, transferred table counts match, valid tombstones remove the
corresponding PostgreSQL items, and no staging objects remain after success.
