# Temporary SQLite importer

I06 provides inspection only. No option transfers data. Remove this directory
in I12 after the owner confirms cutover.

Use Python 3.10 or later and install the isolated dependencies:

```sh
python3 -m venv legacy-import/.venv
legacy-import/.venv/bin/pip install -r legacy-import/requirements.txt
```

Set `LEGACY_SQLITE_PATH` to an existing SQLite snapshot and `DATABASE_URL` to
the prepared PostgreSQL target through your local environment. Then run:

```sh
legacy-import/.venv/bin/python legacy-import/importer.py --dry-run
```

`--sqlite-path` and `--database-url` override the environment. Prefer the
environment for credentials to avoid shell history and process argument exposure.
The CLI does not load `.env` files. Exit status is zero on success and one on
failure. Errors omit underlying driver messages and supplied arguments.

SQLite opens with `mode=ro`, query-only mode, and a read transaction. PostgreSQL
uses one read-only, repeatable-read transaction. All seven canonical domain
tables must exist with their contract columns, be readable, and be empty.
`schema_migrations` may contain applied migrations. Use an operator connection
with SELECT on every domain table, without row-level filtering. Inspection
performs no DDL, writes, sequence changes, or staging. Emptiness is a snapshot
check; a future transfer must recheck after writers stop.

The JSON report includes counts and fixed contract table and column names.
Unrecognized names and SQL definitions are suppressed; only their counts are
shown. Missing optional source tables are reported. The core `users`, `feed`,
and `item` tables and their contract columns are required. A present
`deleted_items` table must have both tombstone columns.

Each tombstone row counts once, including duplicate tombstones:

- `missing`: its item, the item's feed, or its claimed user does not exist.
- `valid`: those records exist and the feed belongs to the claimed user.
- `ownership_mismatched`: those records exist but ownership does not match.

Password counts distinguish nulls, non-text values, plaintext candidates, and
encoded candidates starting with `$`. These are preliminary counts, not hash
validation or authorization to convert values. I06A will validate supported
Argon2id, reject malformed or unsupported encodings, and define normalization.
The report never includes password values, IDs, URLs, titles, or record contents.

## Tombstone staging design for I07

The transfer will create `TEMP TABLE legacy_deleted_items (user_id INTEGER,
item_id INTEGER) ON COMMIT DROP` inside its single import transaction. It will
reference the table as `pg_temp.legacy_deleted_items`, load tombstones after
domain rows, and validate ownership before deletion. Commit drops the table;
rollback undoes its creation. It must never be created in `public`, added to a
migration, or included in `db/schema.sql`. This skeleton does not execute that
DDL. The future import operator will need TEMPORARY privilege on the database.

Run the checks with:

```sh
legacy-import/.venv/bin/python -m unittest discover -s legacy-import -v
```
