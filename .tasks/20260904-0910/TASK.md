# I10 — Prepare the contract for independent releases

- STATUS: DONE
- PRIORITY: 1
- DEPENDS: [I03](../20260904-0903/TASK.md), [I04](../20260904-0904/TASK.md)

## Goal

Define compatible migration rules for independently deployed applications.

## Plan

- [x] Document expand-contract for independent application releases.
- [x] Establish the minimum-version rule: an application checks for its
      required migration ID but permits newer compatible migrations.
- [x] Add a compatibility-section template for new migration PRs.
- [x] Require an explicit compatibility period when removing or renaming a
      shared column.

## Definition of done

A shared column cannot be removed or renamed in a single migration without an
explicit compatibility period.

## Validation

`docs/migrations.md` now defines minimum migration IDs for independently
released applications, the expand-migrate-contract sequence, and the evidence
required to end a compatibility period. The migration PR template records the
affected releases, mixed-version behavior, backfill checks, compatibility
period, lock impact, and grants. `git diff --check` and `make help` passed. No
migration or schema file changed.
