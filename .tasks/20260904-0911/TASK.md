# I11 — Rehearse on disposable PostgreSQL

- STATUS: DONE
- PRIORITY: 1
- DEPENDS: [I01](../20260904-0901/TASK.md), [I02](../20260904-0902/TASK.md), [I03](../20260904-0903/TASK.md), [I04](../20260904-0904/TASK.md), [I05](../20260904-0905/TASK.md), [I06](../20260904-0906/TASK.md), [I07](../20260904-0907/TASK.md), [I08](../20260904-0908/TASK.md), [I09](../20260904-0909/TASK.md), [I10](../20260904-0910/TASK.md)

## Prerequisite

Compatible application versions are ready.

## Goal

Run the complete manual runbook once against disposable PostgreSQL.

## Plan

- [x] Provision a clean schema on disposable PostgreSQL.
- [x] Run the import.
- [x] Verify parser privileges.
- [x] Verify the startup version check.
- [x] Record only discovered defects and required fixes.
- [x] Put fixes in separate follow-up tasks when needed.
- [x] Do not turn the rehearsal into a permanent integration test suite.
- [x] Do not change applications from this task.

## Definition of done

The clean schema, import, parser privileges, and startup version check pass one
complete rehearsal.

## Validation

A PostgreSQL 17 disposable database started empty, applied migrations
`20260904184133` and `20260905082946` with pinned dbmate 2.35.1 in strict mode,
and reported no pending migrations. The rehearsal source passed SQLite
`integrity_check`. Dry-run and execute reports reconciled all seven target
tables and tombstone counts. The import committed, all four identity sequence
probes passed, the temporary tombstone table was absent after commit, and a
repeated execute was rejected because the target was no longer empty.

The parser role read its contract, inserted an item and parser state, and was
denied item deletion and user reads. The parser compatibility command at
revision `03c7a118065190cc7d8fa8b24a518d33bde5e8e4` succeeded through a LOGIN
role with only `gkfeed_parser` membership. An API-role item read and a
parser-role item insert also succeeded. The prepared API PostgreSQL branch
contains storage commit `f6520e68dc39f13ca549b2687e96c8f4b87f026e`, as required
by the runbook.

The rehearsal found one runbook defect. Its step 9 `jq` expression tests
structured `target_before` and `identity_sequences` entries as scalar values,
so it returns false for a valid execute report. Follow-up task I11B records the
required documentation fix. No application, migration, schema, privilege, or
importer code changed in I11.
