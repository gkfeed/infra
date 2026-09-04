# I06 — Add the temporary importer skeleton

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [I04](../20260904-0904/TASK.md)

## Goal

Create a safe dry-run skeleton for the temporary SQLite-to-PostgreSQL importer,
without transferring data yet.

## Plan

- [ ] Create an isolated Python CLI in `legacy-import/` with separate
      dependencies.
- [ ] Accept paths and URLs only through command-line arguments or environment
      variables.
- [ ] Open SQLite read-only.
- [ ] Connect to PostgreSQL and refuse to run if target domain tables are not
      empty.
- [ ] In dry-run mode, print only safe counts and a schema summary.
- [ ] Count legacy `deleted_items` tombstones and classify valid, missing, and
      ownership-mismatched rows without printing their contents.
- [ ] Count plaintext and already-hashed password rows without printing either
      representation.
- [ ] Design the tombstone staging table as transaction-local PostgreSQL state;
      it must never become part of the canonical `public` schema.
- [ ] Never print credentials or record contents.
- [ ] Do not transfer data in this task.

## Definition of done

Dry-run safely shows counts and a schema summary without exposing credentials
or record contents.
