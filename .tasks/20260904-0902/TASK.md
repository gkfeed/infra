# I02 — Define migration rules

- STATUS: DONE
- PRIORITY: 1
- DEPENDS: [I01](../20260904-0901/TASK.md)

## Goal

Define one unambiguous process for working safely with migrations.

## Plan

- [x] Document timestamp-based migration names.
- [x] Establish that applied files are immutable and migrations are
      forward-only.
- [x] Document expand-contract, manual execution, and the ban on application
      DDL.
- [x] Define `public.schema_migrations` as the migration registry.
- [x] Put the operational rules in `AGENTS.md` and link the detailed policy.
- [x] Do not create domain tables in this task.

## Definition of done

A new agent can add a safe migration without making new process decisions.
