# Offline data dump transfer

This procedure keeps the SQLite snapshot and importer on the operator's
computer. It produces a PostgreSQL custom archive that the operator copies to
the production server over SSH.

The archive contains data for the seven contract tables and states for four
identity sequences. It excludes schema definitions, owners, grants,
application LOGIN roles, and `public.schema_migrations`. The server must run
the repository migrations before restore.

## Produce and prove the archive

Stop every SQLite writer before taking the final snapshot. Confirm that
`PRAGMA integrity_check` returns exactly `ok`, then run the full rehearsal:

```sh
scripts/rehearse-dump-transfer.sh \
  /secure/path/gkfeed-cutover.sqlite \
  /secure/path/gkfeed-data.dump
```

The script uses PostgreSQL 17 clients from `postgres:17.10-bookworm`. It does
not use the host `pg_dump`. A successful run proves all of these conditions:

- the importer committed into a clean PostgreSQL 17 cluster;
- importer counts, tombstones, and sequence probes passed;
- the archive TOC contains exactly seven table-data and four sequence-state
  entries;
- restore into a second clean, migrated PostgreSQL 17 cluster succeeded in one
  transaction;
- row counts and SHA-256 hashes of ordered binary table copies match;
- all four sequence states match;
- the SQLite checksum is unchanged.

The output directory is private and ignored by Git. Keep the `.dump`, `.toc`,
`.sha256`, and `rehearsal-evidence` files together. This one-time archive is not
an ongoing backup system.

## Transfer and restore

Copy the archive and checksum through SSH:

```sh
scp /secure/path/gkfeed-data.dump \
    /secure/path/gkfeed-data.dump.sha256 \
    server:/secure/path/
```

On the server, start the empty production container and run all migrations as
described in [PostgreSQL container](container-postgres.md). Check the archive,
then restore it:

```sh
chmod 0400 /secure/path/gkfeed-data.dump \
  /secure/path/gkfeed-data.dump.sha256
DATABASE_URL='<operator URL>' \
  scripts/check-data-dump.sh /secure/path/gkfeed-data.dump
DATABASE_URL='<operator URL>' \
  scripts/restore-data-dump.sh /secure/path/gkfeed-data.dump
```

The restore script refuses a target without both required migrations. It also
refuses a target where any of the seven domain tables contains a row. It checks
the SHA-256 sidecar and restores with `--single-transaction` and
`--exit-on-error`.

After restore, create the application LOGIN roles and run the API and parser
smoke checks. Keep SQLite stopped and unchanged until the owner accepts those
results. Once production PostgreSQL receives the restored rows, do not switch
writers back to SQLite.
