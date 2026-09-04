# I08 — Synchronize sequences and validate INTEGER ranges

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [I07](../20260904-0907/TASK.md)

## Goal

Protect the import from ID overflow and synchronize PostgreSQL sequences after
preserving explicit IDs.

## Plan

- [ ] Before writing, verify that every imported ID fits in PostgreSQL
      `INTEGER`.
- [ ] On overflow, stop the import before changing the target.
- [ ] After import, set each identity or sequence relative to `MAX(id)`.
- [ ] Verify the next generated ID with a safe insert in a rolled-back
      transaction.
- [ ] Do not add a full data-checksum system.

## Definition of done

The next generated ID does not conflict with imported IDs, and range overflow
stops the import before target changes.
