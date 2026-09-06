# Temporary SQLite importer

I06A provides inspection and pure normalization helpers only. No option transfers data. Remove this directory
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

## Feed normalization and reconciliation

Every invocation builds a new plan inside the SQLite read transaction. Run it
again on the final cutover snapshot after stopping writers. I07 must build and
validate this plan from that same snapshot before any target write; an earlier
JSON report is never input to a transfer.

Feeds group by exact `(user_id, url, type)` values. The complete row with the
smallest integer ID survives, including its title when titles differ. The
report gives group counts, duplicate source rows, source count, merged count,
expected target count, and an ordered mapping of every old feed ID to its
preserved ID. Numeric feed IDs are the only record values exposed. URLs,
titles, passwords, and item contents never appear.

`normalization.feed_plan` also returns the preserved full rows and mapping for
I07, kept out of JSON. `normalization.remap_item` returns each full item with
its feed ID replaced and rejects missing feeds. The dry-run checks every item
reference and reports how many need remapping.

Only `item.feed_id` has an approved remapping rule. Any other table with a
`feed_id` column or declared foreign key to `feed` aborts inspection, including
`feed_parser` and `item_hash`, even when empty. Their merge collisions need a
separate policy. Unknown tables also abort because undeclared dependencies
cannot be ruled out. Known legacy `itemhash` and `auth_refresh_tokens` remain
excluded from transfer, provided they declare no feed dependency.

For feeds, `source_count - merged_count = expected_target_count`; the mapping
must contain every source ID and its distinct preserved IDs must match the
target feeds. For items, subtract distinct valid tombstoned item IDs, so repeated
tombstones delete an item only once. Other canonical tables require exact count
equality, treating absent optional tables as zero. The report's `reconciliation`
records these expected counts. Actual target comparison belongs to I07.

## Password validation

The report counts null, supported Argon2id, legacy plaintext, and malformed or
unsupported values. Invalid input aborts with category counts only. Strings
starting with `$`, `{`, `argon2`, `pbkdf2`, `scrypt`, or `bcrypt` are reserved as
encoded representations; invalid ones must never become plaintext input.
Non-text values also fail. All other strings, including empty strings, are
legacy plaintext.

Supported hashes use Argon2id version 19, exactly one each of positive `m`, `t`,
and `p` parameters, 32-bit memory and iteration values, parallelism at most 255,
and memory at least eight times parallelism. Salt and output must be nonempty
unpadded standard base64. This follows the current API decoder in
`api-go/app/internal/passwordhash/passwordhash.go`. Validation does not derive
a hash or verify a password.

`normalization.normalize_password` preserves nulls and supported strings
byte-for-byte. For plaintext it uses the API generation policy: UTF-8, Argon2id
v19, 65536 KiB memory, three iterations, four lanes, a fresh random 16-byte salt,
and a 32-byte output. I07 will call this helper before insertion. Dry-run only
reports the conversion count as `legacy_plaintext`; it never hashes passwords.
Zero conversions is valid when all non-null passwords are already supported.

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
