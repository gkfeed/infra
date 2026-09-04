# I07 — Import confirmed tables

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [I03](../20260904-0903/TASK.md), [I06](../20260904-0906/TASK.md)

## Prerequisite

The I03 contract matrix is fully confirmed.

## Goal

Implement migration of confirmed tables only from SQLite to PostgreSQL.

## Plan

- [ ] Transfer confirmed tables in foreign-key order in one controlled
      operation.
- [ ] Preserve explicit IDs.
- [ ] Treat naive timestamps as UTC.
- [ ] Preserve aware timestamps as the same instant.
- [ ] Do not transfer legacy `itemhash`.
- [ ] Take API-table policies only from the confirmed API contract.
- [ ] Reject repeated runs against a non-empty target.
- [ ] Ensure an error leaves the target clean or explicitly fit only for
      recreation.

## Definition of done

A repeated run against a non-empty target is rejected, failure consequences are
unambiguous, and transferred table counts match.
