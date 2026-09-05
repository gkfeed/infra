# I05 — Add group roles and grants

- STATUS: DONE
- PRIORITY: 1
- DEPENDS: [I04](../20260904-0904/TASK.md)

## Goal

Give applications the minimum required privileges without adding users or
secrets.

## Plan

- [x] Create NOLOGIN application roles in a forward migration.
- [x] Grant parser `SELECT` on `feed` and the required operations on `item`,
      `feed_parser`, and `item_hash`.
- [x] Grant API the required operations on API-owned tables, including
      `DELETE` on `item`; do not grant the parser item deletion.
- [x] Grant access to required sequences and `SELECT` on `schema_migrations`.
- [x] Do not grant DDL privileges to applications.
- [x] Do not create specific LOGIN users or add passwords.
- [x] Document smoke checks for allowed and forbidden operations for both the
      parser and API roles.

## Definition of done

The documented smoke checks confirm both application roles' allowed and
forbidden operations, including parser insert and API delete on `item`.

## Validation

On disposable PostgreSQL 17, `make migrate`, `make status`, and `make dump`
passed with pinned dbmate 2.35.1 in strict mode. Both migrations are applied
and none are pending. `checks/application_roles.sql` passed the allowed and
forbidden operation checks for both roles. See `docs/application-roles.md`.
