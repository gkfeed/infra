# I09 — Document the manual cutover

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [I05](../20260904-0905/TASK.md), [I08](../20260904-0908/TASK.md)

## Goal

Create a short, unambiguous runbook for the manual SQLite-to-PostgreSQL
cutover.

## Plan

- [ ] Document stopping SQLite writers and preserving a SQLite copy.
- [ ] Document preparing a clean PostgreSQL instance and running
      `dbmate migrate`.
- [ ] Document running the importer and comparing counts.
- [ ] Document creating LOGIN roles outside Git.
- [ ] Document switching applications and starting parser after its version
      check.
- [ ] Give every step a command or unambiguous check.
- [ ] Explicitly mark the point of no return: after PostgreSQL writes begin,
      switching back to SQLite is forbidden.
- [ ] Do not automate deployment in this task.

## Definition of done

Every step has a command or unambiguous check, and the point of no return is
explicitly marked.
