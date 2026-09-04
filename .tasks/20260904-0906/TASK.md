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
- [ ] Never print credentials or record contents.
- [ ] Do not transfer data in this task.

## Definition of done

Dry-run safely shows counts and a schema summary without exposing credentials
or record contents.
