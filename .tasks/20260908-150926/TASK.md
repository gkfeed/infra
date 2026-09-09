# I13: Add production PostgreSQL Compose and offline dump transfer

- STATUS: IN PROGRESS
- PRIORITY: 1
- DEPENDS: [I11C](../20260908-115358/TASK.md)

## Goal

Run the production PostgreSQL database from this repository and support a
rehearsed, operator-applied data-only dump transfer from the final SQLite
snapshot.

## Plan

- [x] Add a loopback-only PostgreSQL 17 production Compose service with a
      persistent host bind mount, health check, and bounded container logs.
- [x] Add an isolated named-volume overlay for transfer rehearsal.
- [x] Keep real credentials in ignored mode-0600 environment files.
- [x] Export only the seven contract tables and four identity sequence states.
- [x] Exclude schema, owners, ACLs, LOGIN roles, and `schema_migrations` from
      the archive.
- [x] Reject an unexpected archive TOC or a nonempty restore target.
- [x] Rehearse import, export, restore, table hashes, counts, and sequences on
      the current production SQLite snapshot.
- [x] Leave the restored rehearsal database running for API and parser checks.
- [x] Document production startup and the operator-applied restore.

## Definition of done

The custom archive restores into a second clean PostgreSQL 17 cluster after
normal migrations. Every transferred table and sequence matches the imported
source. The production Compose file stores data outside the repository and
does not expose PostgreSQL beyond loopback.

## Validation

The mode-0400 SQLite snapshot at the private operator path passed
`PRAGMA integrity_check` and retained the same SHA-256 before and after the
run. Both clean clusters used `postgres:17.10-bookworm` and applied migrations
`20260904184133` and `20260905082946` with pinned dbmate 2.35.1.

Dry-run and execute reports passed their gates and reconciliation diffs. The
import committed and every identity sequence probe passed. The custom archive
TOC contained exactly seven `TABLE DATA` and four `SEQUENCE SET` entries. It
contained no schema, owner, ACL, LOGIN, or `schema_migrations` data entry.

Restore into the second clean migrated cluster completed with
`--single-transaction` and `--exit-on-error`. Counts and SHA-256 hashes of
ordered binary copies matched for all seven tables. All four sequence states
matched. A repeated restore was rejected by the nonempty-target check.

Both rehearsal LOGIN identities authenticated with passwords from the private
restore environment. API could read `users` but not `feed_parser`; parser
could read `feed` but not `users`. Both could read the two migration registry
rows. The restored cluster remains healthy on loopback for application smoke
tests. Keep this task in progress until API and parser checks pass.
