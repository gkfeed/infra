# I17: Add item change history for API sync

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: none

## Problem

The API sync routes in [gkfeed/api#12](https://github.com/gkfeed/api/pull/12)
need a durable, user-scoped history of
item inserts, updates, and deletes. The API reads this history but does not own
production DDL. Without the table and triggers, the new routes cannot work.
The API also refuses to start until its required migration ID appears in
`public.schema_migrations`.

## Goal

Provide the `item_changes` database contract before deploying the API sync
release. Preserve the existing parser and API database permissions.

## Plan

- [ ] Create a forward-only migration with `make new NAME=add_item_changes`.
      Use the SQL in `docs/infra/20260923000000_item_changes.sql` from
      gkfeed/api#12 as the starting point, then review it against the infra
      migration policy.
- [ ] Add the indexed `item_changes` table and grant the API role only the
      required `SELECT` privilege. Record an item payload for inserts and
      updates, and a tombstone for deletes. Cover deletes caused by feed
      deletion, including database cascades.
- [ ] Ensure per-user change IDs cannot become visible out of commit order,
      so a client cannot advance its cursor past a late-committing change.
- [ ] Add PostgreSQL checks for insert, update, item delete, feed delete,
      user isolation, payload fields, ordering under concurrent transactions,
      and API/parser role privileges.
- [ ] Update `contracts/api.md` and regenerate `db/schema.sql` with `make dump`.
- [ ] Coordinate the migration ID with gkfeed/api#12 before either release.
      The API currently requires `20260923000000`, but infra policy assigns
      the ID through `make new`. Update the API startup check and its docs to
      the actual generated ID; do not rename the generated migration by hand.
- [ ] Merge and apply the infra migration through the designated operator,
      verify it in `public.schema_migrations`, then deploy the API release.

## Definition of done

The API can read complete, correctly ordered item changes for one user with
`SELECT` access to `item_changes`. Inserts, updates, and deletes through either
application or database cascade appear in the history. The applied migration
ID matches the API startup requirement, and the migration is in production
before the API sync release starts.
