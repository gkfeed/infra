# I04 — Add the canonical base schema

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [I03](../20260904-0903/TASK.md)

## Prerequisite

The owner has confirmed the API contract from I03.

## Goal

Create the agreed canonical PostgreSQL schema in the first migration.

## Plan

- [ ] Create the agreed shared and application-specific tables in `public` in a
      single initial migration.
- [ ] Use `INTEGER` IDs and explicit nullability for parser.
- [ ] Add `item.feed_id` with a foreign key.
- [ ] Add `feed_parser.feed_id` and `item_hash.feed_id` with cascading foreign
      keys.
- [ ] Add `UNIQUE(feed_id, hash)`.
- [ ] Use `TIMESTAMPTZ` for contract timestamp fields.
- [ ] Exclude legacy `itemhash` and SQLite-only tables without a confirmed
      contract.
- [ ] Update `schema.sql`.

## Definition of done

A clean PostgreSQL instance can be provisioned with one dbmate command, and
`schema.sql` shows the exact shared contract.
