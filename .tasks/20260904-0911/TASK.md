# I11 — Rehearse on disposable PostgreSQL

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [I01](../20260904-0901/TASK.md), [I02](../20260904-0902/TASK.md), [I03](../20260904-0903/TASK.md), [I04](../20260904-0904/TASK.md), [I05](../20260904-0905/TASK.md), [I06](../20260904-0906/TASK.md), [I07](../20260904-0907/TASK.md), [I08](../20260904-0908/TASK.md), [I09](../20260904-0909/TASK.md), [I10](../20260904-0910/TASK.md)

## Prerequisite

Compatible application versions are ready.

## Goal

Run the complete manual runbook once against disposable PostgreSQL.

## Plan

- [ ] Provision a clean schema on disposable PostgreSQL.
- [ ] Run the import.
- [ ] Verify parser privileges.
- [ ] Verify the startup version check.
- [ ] Record only discovered defects and required fixes.
- [ ] Put fixes in separate follow-up tasks when needed.
- [ ] Do not turn the rehearsal into a permanent integration test suite.
- [ ] Do not change applications from this task.

## Definition of done

The clean schema, import, parser privileges, and startup version check pass one
complete rehearsal.
