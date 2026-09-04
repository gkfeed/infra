# I04 — Add the canonical base schema

- STATUS: DONE
- PRIORITY: 1
- DEPENDS: [I03](../20260904-0903/TASK.md)

## Prerequisite

The owner has confirmed the API contract from I03.

## Goal

Create the agreed canonical PostgreSQL schema in the first migration.

## Plan

- [x] Create the agreed shared and application-specific tables in `public` in a
      single initial migration.
- [x] Use `INTEGER` IDs and explicit nullability for parser.
- [x] Add `item.feed_id` with `ON DELETE CASCADE` so an API-owned feed delete
      atomically removes its items.
- [x] Add `feed_parser.feed_id` and `item_hash.feed_id` with cascading foreign
      keys.
- [x] Add `UNIQUE(feed_id, hash)`.
- [x] Use `TIMESTAMPTZ` for contract timestamp fields.
- [x] Exclude legacy `itemhash` and SQLite-only tables without a confirmed
      contract.
- [x] Do not create `deleted_items` in the canonical `public` schema; it is
      temporary input for the legacy importer only.
- [x] Update `schema.sql`.

## Definition of done

A clean PostgreSQL instance can be provisioned with one dbmate command, and
`schema.sql` shows the exact shared contract.
