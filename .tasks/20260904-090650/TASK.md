# I06A — Define importer normalization and credential checks

- STATUS: DONE
- PRIORITY: 1
- DEPENDS: [I06](../20260904-0906/TASK.md)

## Goal

Turn legacy feed duplicates and password representations into explicit,
testable importer rules before any data is transferred.

## Feed normalization

- [x] In dry-run, group feeds by `(user_id, url, type)` and report the number
      of groups, source rows, and rows that will remain after normalization.
- [x] For every repeated group, preserve the complete row with the smallest
      feed ID, including its `title`.
- [x] Produce a safe old-ID-to-preserved-ID mapping in the operator report.
      Do not print feed URLs, titles, credentials, or item contents.
- [x] Remap every imported `item.feed_id` from a removed feed ID to the
      preserved ID before insertion.
- [x] Re-run duplicate and dependency checks against the cutover snapshot. Do
      not rely on counts collected from an earlier copy of SQLite.
- [x] Abort before target writes if the source contains a dependent table that
      the importer cannot remap safely.

## Password checks

- [x] Classify `users.hashed_password` as null, supported Argon2id, legacy
      plaintext, or malformed or unsupported encoded data without printing
      any value.
- [x] Preserve supported Argon2id strings byte-for-byte.
- [x] Convert only legacy plaintext with the API-compatible Argon2id policy.
- [x] Abort before target writes when a value looks encoded but is malformed
      or unsupported. Never hash that value as plaintext.
- [x] Report only category counts. A result with zero converted passwords is
      valid when every non-null password is already encoded correctly.

## Reconciliation contract

- [x] Replace raw feed table-count equality with an explicit reconciliation:
      source count, merged count, target count, and the ID mapping must agree.
- [x] Keep exact count equality for tables that are not intentionally changed
      by tombstone deletion or feed normalization.
- [x] Add fixtures for equal-title duplicates, different-title duplicates,
      dependencies that require remapping, valid Argon2id, plaintext, null,
      and malformed encoded passwords.
- [x] Do not transfer data in this task.

## Definition of done

Dry-run deterministically describes every feed merge and password action,
exposes no record contents or credentials, and refuses ambiguous input before
PostgreSQL is changed.

## Validation

All nine importer unittest checks passed, including disposable PostgreSQL 17
integration, empty-target rejection checks, and malformed-password rejection
with every target domain table still empty. Fixtures cover both duplicate title
cases, item remapping, unsupported dependencies, fresh snapshot planning,
password categories, and output redaction. The current Go API verifier accepted
Python-generated hashes for ASCII, empty, and Unicode passwords.

Pinned dbmate 2.35.1 passed `make migrate`, `make status`, and `make dump` in
strict mode. Both existing migrations are applied with none pending. The dump
had only a server-version comment difference, which was kept unchanged.
No migration or transfer mode was added. I07 will consume the normalization
helpers and compare actual target rows with this task's reconciliation plan.
