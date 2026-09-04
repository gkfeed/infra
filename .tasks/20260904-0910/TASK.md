# I10 — Prepare the contract for independent releases

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [I03](../20260904-0903/TASK.md), [I04](../20260904-0904/TASK.md)

## Goal

Define compatible migration rules for independently deployed applications.

## Plan

- [ ] Document expand-contract for independent application releases.
- [ ] Establish the minimum-version rule: an application checks for its
      required migration ID but permits newer compatible migrations.
- [ ] Add a compatibility-section template for new migration PRs.
- [ ] Require an explicit compatibility period when removing or renaming a
      shared column.

## Definition of done

A shared column cannot be removed or renamed in a single migration without an
explicit compatibility period.
