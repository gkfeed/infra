# Temporary SQLite importer

The importer provides a controlled SQLite-to-PostgreSQL transfer. Remove this directory
in I12 after the owner confirms cutover.

Use Python 3.10 or later and install the isolated dependencies:

```sh
python3 -m venv legacy-import/.venv
legacy-import/.venv/bin/pip install -r legacy-import/requirements.txt
```

Set `LEGACY_SQLITE_PATH` to an existing SQLite snapshot and `DATABASE_URL` to
the prepared PostgreSQL target through the local environment. Inspect without
changing either database:

```sh
legacy-import/.venv/bin/python legacy-import/importer.py --dry-run
```

Transfer into an empty target:

```sh
legacy-import/.venv/bin/python legacy-import/importer.py --execute
```

The default remains dry-run when neither mode flag is present. `--dry-run` and
`--execute` are mutually exclusive. Only explicit `--execute` permits
PostgreSQL writes. `--sqlite-path` and `--database-url` override the environment.
Prefer the environment for credentials to avoid shell history and process
argument exposure. The CLI does not load `.env` files. Exit status is zero on
success and one on failure. Errors omit driver messages and supplied arguments.

SQLite opens with `mode=ro`, query-only mode, and a read transaction. Dry-run
uses one read-only, repeatable-read PostgreSQL transaction. Execute uses one
serializable PostgreSQL transaction, locks all seven domain tables, and checks
their schema and emptiness after taking the locks. All seven tables must exist
with their contract columns, be readable, and be empty. `schema_migrations` may
contain applied migrations.

Execute builds a fresh plan from the same SQLite read transaction, inserts in
foreign-key order, reconciles every target count, and commits once. Any error
rolls the complete operation back. A second execute against the populated target
is rejected. The operator connection needs SELECT and INSERT on the domain
tables, TEMPORARY on the database, and ownership of the four identity sequences
for transactional `ALTER SEQUENCE ... RESTART`. It must see all rows without
row-level filtering. Use the infra operator connection.

The JSON report includes counts and fixed contract table and column names.
Unknown tables abort the operation without exposing their names. The approved
source-only `log` and unfinished `item_hash_new` tables are allowed only when
their approved column and key fingerprints match; their counts are reported and
their data is not transferred. Missing optional source tables are reported. The core
`users`, `feed`, and `item` tables and their contract columns are required. A
present `deleted_items` table must have both tombstone columns.

## Tombstones

Each tombstone row counts once, including duplicates:

- `missing`: its item, the item's feed, or its claimed user does not exist.
- `valid`: those records exist and the feed belongs to the claimed user.
- `ownership_mismatched`: those records exist but ownership does not match.

The source plan contains the distinct item IDs covered by valid tombstones.
Execute skips those items before converting or inserting their contents. It
creates `TEMP TABLE legacy_valid_tombstoned_items (item_id INTEGER PRIMARY KEY)
ON COMMIT DROP`, referenced as `pg_temp.legacy_valid_tombstoned_items`, and
loads the planned IDs. A PostgreSQL join then verifies that none of those IDs
exists in `public.item`. Missing and ownership-mismatched tombstones remain in
the aggregate report but do not exclude an item. Commit drops the table;
rollback undoes its creation. It is never created in `public`, added to a
migration, or included in `db/schema.sql`.

## Feed and parser-state normalization

Every invocation builds a new plan inside the SQLite read transaction. Run it
again on the final cutover snapshot after stopping writers. An earlier JSON
report is never input to a transfer.

Feeds group by exact `(user_id, url, type)` values. The complete row with the
smallest integer ID survives, including its title when titles differ. The report
gives group counts, duplicate source rows, source count, merged count, expected
target count, and an ordered mapping of every old feed ID to its preserved ID.
Numeric feed IDs are the only record values exposed. URLs, titles, passwords,
hashes, and item contents never appear.

Items referencing a missing feed are legacy orphans. They are counted and not
transferred. Other items remap to the preserved feed. Unknown feed dependencies
abort because the importer cannot infer a safe rule. Known legacy `itemhash` and
`auth_refresh_tokens` remain excluded, provided they declare no feed dependency.

`feed_parser` rows referencing missing feeds are counted and discarded. When
feed normalization maps several parser rows to one feed, the earliest
`valid_for` wins. This avoids delaying the next fetch. Naive timestamps are UTC;
aware timestamps preserve their instant.

`item_hash` rows referencing missing feeds are counted and discarded. Other
feed IDs are remapped. A collision on `(feed_id, hash)` keeps the row with the
smallest original ID. Rows with null `feed_id` remain distinct legacy rows.

For feeds, `source_count - merged_count = expected_target_count`; the mapping
must contain every source ID and its distinct preserved IDs must match target
feeds. For items, reconciliation subtracts orphan items and distinct valid
tombstoned items. Parser-state reconciliation subtracts orphan and merged rows.
Other canonical tables require exact count equality, treating absent optional
tables as zero. Execute compares every actual target count before commit.

The private [orphan item analysis tool](orphan-item-analysis/README.md) can
export full records when aggregate counts are insufficient for an operator
decision. Its output is ignored by Git and must be deleted after analysis.

## Password validation

The report counts null, supported Argon2id, legacy plaintext, and malformed or
unsupported values. Invalid input aborts with category counts only. Strings
starting with `$`, `{`, `argon2`, `pbkdf2`, `scrypt`, or `bcrypt` are reserved as
encoded representations; invalid ones never become plaintext input. Non-text
values also fail. All other strings, including empty strings, are legacy
plaintext.

Supported hashes use Argon2id version 19, exactly one each of positive `m`, `t`,
and `p` parameters, 32-bit memory and iteration values, parallelism at most 255,
and memory at least eight times parallelism. Salt and output must be nonempty
unpadded standard base64. This follows the current API decoder in
`api-go/app/internal/passwordhash/passwordhash.go`.

`normalization.normalize_password` preserves nulls and supported strings
byte-for-byte. For plaintext it uses UTF-8, Argon2id v19, 65536 KiB memory, three
iterations, four lanes, a fresh random 16-byte salt, and a 32-byte output.
Execute calls it immediately before insertion. Dry-run only reports the
conversion count.

## Private output

The JSON operator report contains numeric feed ID mappings. Treat a saved full
report as private production-derived data. Long-lived rehearsal evidence should
keep only aggregate counts and a mapping checksum. Never save record contents,
credentials, hashes, connection URLs, or driver messages.

## Integer IDs and sequences

Before any target writes, both modes check every integer ID and reference in
present canonical source tables and `deleted_items`. Values must be integers
between -2147483648 and 2147483647. Only `item_hash.feed_id` and tombstone
columns accept null. Token text IDs and WebAuthn binary IDs are not integer
columns. Checks include rows that normalization would discard; excluded legacy
tables are not checked. Errors contain no offending values.

An identity ID of 2147483647 is rejected before writes because it leaves no
room for a generated ID. This conservative check also includes rows that would
be merged, orphaned, or excluded.

After tombstone exclusion and count reconciliation, execute restarts the `users`,
`feed`, `item`, and `item_hash` identity sequences at `max(1, MAX(id) + 1)`.
Empty tables and tables containing only nonpositive IDs start at 1. It discovers
each sequence through `pg_get_serial_sequence`.

Execute inserts a temporary user, feed, item, and item hash using generated IDs
inside a savepoint and checks the returned IDs. It rolls back those rows and
restarts the sequences again so the probes consume no application IDs. The
report contains a verification flag for each sequence. Sequence restarts and
domain writes share the import transaction, so an error restores both. This
uses transactional `ALTER SEQUENCE ... RESTART`, not nontransactional `setval`.
No permanent schema change or new migration is needed.

Run all permanent checks with a disposable PostgreSQL URL:

```sh
IMPORT_TEST_DATABASE_URL=postgresql://... \
  legacy-import/.venv/bin/python -m unittest discover -s legacy-import -v
legacy-import/.venv/bin/python -m unittest discover \
  -s legacy-import/orphan-item-analysis -v
```
