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
| `item_id_seq`, `item_hash_id_seq` | USAGE | None |
| `feed_id_seq` | None | USAGE |

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

## Smoke checks

Use a clean disposable PostgreSQL instance and an operator connection in
`DATABASE_URL`. Do not run these checks against production. The script rolls
back its fixture rows and helper function, but identity sequences advance.

```sh
make migrate
make status
make dump
psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -f checks/application_roles.sql
```

The operator must be able to `SET ROLE` to both application groups and create a
temporary helper function. The helper runs with caller privileges and accepts
only SQLSTATE `42501`, insufficient privilege, as an expected denial. Any
unexpected success or other SQL error fails the check.

The script exercises every allowed table operation, including generated IDs,
parser state upsert, legacy hash assignment, API item deletion, and feed
cascades. It also checks forbidden writes, access to the other application's
private tables, sequence resets, registry writes, table alteration and removal,
TRUNCATE, and permanent and temporary object creation. Both roles must remain
NOLOGIN without elevated attributes. Success ends with
`Application role smoke checks passed.`

Validated on disposable PostgreSQL 17 with dbmate 2.35.1. Both migrations were
applied, `make status` reported zero pending migrations, and all smoke checks
passed.
