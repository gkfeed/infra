# I06A — Define importer normalization and credential checks

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [I06](../20260904-0906/TASK.md)

## Goal

Turn legacy feed duplicates and password representations into explicit,
testable importer rules before any data is transferred.

## Feed normalization

- [ ] In dry-run, group feeds by `(user_id, url, type)` and report the number
      of groups, source rows, and rows that will remain after normalization.
- [ ] For every repeated group, preserve the complete row with the smallest
      feed ID, including its `title`.
- [ ] Produce a safe old-ID-to-preserved-ID mapping in the operator report.
      Do not print feed URLs, titles, credentials, or item contents.
- [ ] Remap every imported `item.feed_id` from a removed feed ID to the
      preserved ID before insertion.
- [ ] Re-run duplicate and dependency checks against the cutover snapshot. Do
      not rely on counts collected from an earlier copy of SQLite.
- [ ] Abort before target writes if the source contains a dependent table that
      the importer cannot remap safely.

## Password checks

- [ ] Classify `users.hashed_password` as null, supported Argon2id, legacy
      plaintext, or malformed or unsupported encoded data without printing
      any value.
- [ ] Preserve supported Argon2id strings byte-for-byte.
- [ ] Convert only legacy plaintext with the API-compatible Argon2id policy.
- [ ] Abort before target writes when a value looks encoded but is malformed
      or unsupported. Never hash that value as plaintext.
- [ ] Report only category counts. A result with zero converted passwords is
      valid when every non-null password is already encoded correctly.

## Reconciliation contract

- [ ] Replace raw feed table-count equality with an explicit reconciliation:
      source count, merged count, target count, and the ID mapping must agree.
- [ ] Keep exact count equality for tables that are not intentionally changed
      by tombstone deletion or feed normalization.
- [ ] Add fixtures for equal-title duplicates, different-title duplicates,
      dependencies that require remapping, valid Argon2id, plaintext, null,
      and malformed encoded passwords.
- [ ] Do not transfer data in this task.

## Definition of done

Dry-run deterministically describes every feed merge and password action,
exposes no record contents or credentials, and refuses ambiguous input before
PostgreSQL is changed.
