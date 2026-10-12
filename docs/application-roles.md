# Application roles

Migration `20260905082946` creates `gkfeed_parser` and `gkfeed_api` as NOLOGIN
group roles. Their grants follow [parser](../contracts/parser.md) and
[API](../contracts/api.md).

| Object | Parser | API |
| --- | --- | --- |
| `schema_migrations` | SELECT | SELECT |
| `users` | None | SELECT, UPDATE of `hashed_password` |
| `feed` | SELECT | SELECT, INSERT, DELETE |
| `item` | SELECT, INSERT | SELECT, DELETE |
| `feed_parser` | SELECT, INSERT, UPDATE of `valid_for` | None |
| `item_hash` | SELECT, INSERT, UPDATE of `feed_id` | None |
| `webauthn_credentials` | None | SELECT, INSERT, UPDATE, DELETE |
| `refresh_tokens` | None | SELECT, INSERT, DELETE |
| `browser_sessions` | None | SELECT, INSERT, UPDATE, DELETE |
| `item_changes` | None | SELECT |
| `item_id_seq`, `item_hash_id_seq` | USAGE | None |
| `feed_id_seq` | None | USAGE |

Migration `20260927071753` adds the `item_changes` read grant to `gkfeed_api`
and `gkfeed_backup`. The backup role can also read `item_changes_id_seq`.
Neither application role can write change rows or use the new identity
sequence. Security-definer triggers write the rows when items change or a feed
is deleted.

Migration `20261012101552` adds browser sessions. The API needs `UPDATE` to
renew activity; its `refresh_tokens` privileges remain SELECT, INSERT, DELETE.
The backup role receives SELECT on `browser_sessions`. The table adds no
sequence, and neither application role owns it.

Both roles have USAGE on `public`. Sequence USAGE permits generated IDs but
not `setval`. User provisioning remains an operator responsibility, so neither
application receives INSERT on `users` or access to `users_id_seq`.

API feed deletion cascades to items, parser state, and hashes through the
existing foreign keys. It does not require direct API grants on parser tables.
The parser cannot delete items, including items it inserted.

## Operator requirements

Run merged migrations manually with the pinned `make` targets as a role that
can create roles and manage the database, schema, and table grants. These role
names are cluster-wide and must be unused before this migration. A conflicting
role makes the migration fail instead of reusing potentially privileged state.

The migration revokes `PUBLIC` CREATE on `public` and `PUBLIC` CREATE and
TEMPORARY on the current database. This also removes inherited permissions
from other ordinary roles in that database. An operator must explicitly grant
any required permissions to non-application tooling.

Create application LOGIN identities and assign group membership outside Git.
Each identity must inherit only its application's group, have no elevated role
attributes or extra grants, and own no database objects. Combining both groups
would combine their permissions. Application roles must never own the database,
schema, tables, or migration registry.

No default grants cover future tables or sequences. Each migration must grant
only the access its consumers require. The dbmate schema dump omits role
creation and ACLs, so provision through migrations, not `db/schema.sql` alone.

## Backup role

Migration `20260911093048` creates `gkfeed_backup` as a separate NOLOGIN group.
It has CONNECT and schema USAGE plus SELECT on every current table and sequence.
It cannot change data, advance sequences, create temporary objects, or perform
DDL. Operators create its LOGIN identity and password outside Git.

Run the backup role check only against a disposable migrated database:

```sh
psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -f checks/backup_role.sql
```

The check confirms every required read and rejects writes, sequence changes,
temporary objects, and DDL. Every migration that adds a backed-up table or
sequence must explicitly grant its read access to `gkfeed_backup`.

## Smoke checks

Use a clean disposable PostgreSQL instance and an operator connection in
`DATABASE_URL`. Do not run these checks against production. The script rolls
back its fixture rows and helper function, but identity sequences advance.

```sh
make migrate
make status
make dump
psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -f checks/application_roles.sql
psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -f checks/item_changes.sql
psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -f checks/browser_sessions.sql
psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -f checks/backup_role.sql
python checks/item_changes_concurrency.py
```

The operator must be able to `SET ROLE` to both application groups and create a
temporary helper function. The helper runs with caller privileges and accepts
only SQLSTATE `42501`, insufficient privilege, as an expected denial. Any
unexpected success or other SQL error fails the check.

The script exercises every allowed table operation, including generated IDs,
parser state upsert, hash feed assignment, API item deletion, and feed
cascades. It also checks forbidden writes, access to the other application's
private tables, sequence resets, registry writes, table alteration and removal,
TRUNCATE, and permanent and temporary object creation. Both roles must remain
NOLOGIN without elevated attributes. Success ends with
`Application role smoke checks passed.`

The item change check covers payloads, direct and cascade tombstones, user
isolation, and read-only grants. The concurrency check requires psycopg 3 and
uses two transactions to verify that a later change for one user waits for the
earlier transaction to commit.

The browser session check runs API queries under `gkfeed_api`, verifies digest
and timestamp constraints, user foreign keys and deletion restrictions, and
checks expiry, logout, role ownership, and DDL denials.

Validated on disposable PostgreSQL 17.10 with dbmate 2.35.1 through migration
`20261012101552`. `make status` reported five applied migrations and zero
pending migrations, and all smoke checks passed.
