# I02 — Define migration rules

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [I01](../20260904-0901/TASK.md)

## Goal

Define one unambiguous process for working safely with migrations.

## Plan

- [ ] Document timestamp-based migration names.
- [ ] Establish that applied files are immutable and migrations are
      forward-only.
- [ ] Document expand-contract, manual execution, and the ban on application
      DDL.
- [ ] Define `public.schema_migrations` as the migration registry.
- [ ] Do not create domain tables in this task.

## Definition of done

A new agent can add a safe migration without making new process decisions.
