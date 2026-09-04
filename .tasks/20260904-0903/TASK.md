# I03 — Build the application contract matrix

- STATUS: DONE
- PRIORITY: 1
- DEPENDS: [I02](../20260904-0902/TASK.md)

## Goal

Build the actual PostgreSQL contract matrix for parser and API before designing
the first schema.

## Plan

- [x] Inspect the current parser and API read-only.
- [x] Create `contracts/parser.md` and `contracts/api.md`.
- [x] For each application, document tables and columns, read and write
      operations, data ownership, and required foreign keys.
- [x] Document the parser contract: reading `feed`, creating and reading `item`,
      and managing `feed_parser` and `item_hash`.
- [x] Explicitly mark disputed API decisions instead of guessing them.
- [x] Do not write DDL or change application code.

## Definition of done

Application overlaps and differences are visible before the first schema is
designed, and disputed API decisions are explicitly marked.
