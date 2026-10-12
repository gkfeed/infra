# Browser session rollout

Migration `20261012101552_add_browser_sessions.sql` provides the database
contract required by [API PR #7](https://github.com/gkfeed/api/pull/7).
The table and grants are recorded in [the API contract](../contracts/api.md).
The foreign key uses the canonical `users.id` INTEGER primary key and
`ON DELETE RESTRICT`. An operator must remove a user's sessions before
deleting that user. Applications cannot provision or delete users.

## Release order

1. Merge this infra PR. A designated operator applies migration
   `20261012101552` with `make status`, `make migrate`, and `make status`.
   Follow [the migration policy](migrations.md). No application deployment
   runs these commands.
2. Deploy the API release from PR #7 after the schema and grants are present.
   The new database contract starts at migration `20261012101552`. Record
   this minimum in the consuming API release. Its startup column check must
   pass under the application role before it serves traffic.
3. Transition the frontend in a separate release after infra and API are
   ready. Replace saved credentials with cookie login, remove
   `gkfeed.credentials`, require a fresh login, and restore sessions with
   `GET /api/v2/me`. Follow the API's browser-session documentation for
   Origin configuration and the local development proxy.

This is an additive migration. Existing API and parser releases continue to
use their tables and grants. Old and new API instances can run together;
route browser-session requests to the new API until all instances support
them. No backfill or removal of the legacy refresh-token contract is needed.
This task prepares the migration and checks only; applying it to shared
databases, deploying the API, and changing the frontend are separate work.

## Validation

Use a separate disposable PostgreSQL 17 instance. Run `make migrate`,
`make status`, and `make dump`, then the smoke checks listed in
[application roles](application-roles.md). The browser session check uses
`SET LOCAL ROLE gkfeed_api` and rolls back its fixture rows. Identity sequences
still advance. Existing role, backup, item-change, and concurrency checks
must continue to pass.

## Rollback

The migration has an empty `migrate:down`. Do not run dbmate down or edit the
migration registry. Rolling back the API release can leave this additive
table and its grants in place.

If the schema must be removed, first stop every browser-session consumer and
accept that existing cookies will be revoked. Create a new migration with
`make new NAME=remove_browser_sessions`. Its up section may use
`DROP TABLE public.browser_sessions` without CASCADE, and its down section
must remain empty. Dropping the table also removes its indexes, constraints,
and grants. Test that forward migration on a disposable instance, run
`make status` and `make dump`, and submit it in a separate reviewed PR.
The original migration ID remains in `public.schema_migrations`.

## Expired-row maintenance

The API rejects expired sessions even while their rows remain. An operator
can remove expired rows in a separate maintenance operation:

```sql
DELETE FROM public.browser_sessions
WHERE expires_at <= CURRENT_TIMESTAMP
   OR last_seen_at <= CURRENT_TIMESTAMP - INTERVAL '30 days';
```

Choose bounded batches if the table becomes large. This migration does not
install a scheduler. Backup access is read-only through `gkfeed_backup`;
session digests should receive the same access controls as other auth data.
