# I09 — Document the manual cutover

- STATUS: DONE
- PRIORITY: 1
- DEPENDS: [I05](../20260904-0905/TASK.md), [I08](../20260904-0908/TASK.md)

## Goal

Create a short, unambiguous runbook for the manual SQLite-to-PostgreSQL
cutover.

## Plan

- [x] Document stopping SQLite writers and preserving a SQLite copy.
- [x] Document preparing a clean PostgreSQL instance and running
      `dbmate migrate`.
- [x] Document running the importer and comparing counts.
- [x] Document verifying tombstone cleanup statistics and confirming that the
      temporary PostgreSQL staging table no longer exists.
- [x] State that the library storage-seam API change is merged and deployed
      only after PostgreSQL schema, grants, import, and cleanup are ready; it is
      not a SQLite production transition release.
- [x] Document creating LOGIN roles outside Git.
- [x] Document switching applications and starting parser after its version
      check.
- [x] Give every step a command or unambiguous check.
- [x] Explicitly mark the point of no return: after PostgreSQL writes begin,
      switching back to SQLite is forbidden.
- [x] Do not automate deployment in this task.

## Definition of done

Every step has a command or unambiguous check, and the point of no return is
explicitly marked.

## Validation

The runbook uses the pinned infra `make` targets and the importer's current CLI
and JSON fields. Its release gates match API storage commit `f6520e6`, API
minimum migration `20260905082946`, and parser compatibility-check commit
`03c7a11`. No migration, importer, application, or deployment code changed.
