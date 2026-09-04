# I01 — Create the minimal infra repository

- STATUS: DONE
- PRIORITY: 1
- DEPENDS: none

## Goal

Create the minimal skeleton for the separate `gkfeed/infra` repository without
adding a domain schema.

## Plan

- [x] Create `AGENTS.md`, `README.md`, `.gitignore`, and `Makefile`.
- [x] Create the `db/migrations/` directory.
- [x] Configure a pinned dbmate version.
- [x] Add `migrate`, `status`, `new`, and `dump` commands that always use
      `--strict`.
- [x] Do not add a schema in this task.

## Definition of done

A fresh checkout shows help and status against a configured `DATABASE_URL`.
