# I05 — Add group roles and grants

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [I04](../20260904-0904/TASK.md)

## Goal

Give applications the minimum required privileges without adding users or
secrets.

## Plan

- [ ] Create NOLOGIN application roles in a forward migration.
- [ ] Grant parser `SELECT` on `feed` and the required operations on `item`,
      `feed_parser`, and `item_hash`.
- [ ] Grant access to required sequences and `SELECT` on `schema_migrations`.
- [ ] Do not grant DDL privileges to applications.
- [ ] Do not create specific LOGIN users or add passwords.
- [ ] Document smoke checks for allowed and forbidden parser-role operations.

## Definition of done

The documented smoke checks confirm the parser role's allowed and forbidden
operations.
