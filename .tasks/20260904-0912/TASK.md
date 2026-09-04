# I12 — Remove the SQLite importer after cutover

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: none; see external prerequisites below

## Prerequisites

- Cutover is complete.
- PostgreSQL operation is confirmed.
- The owner has explicitly decided to remove the legacy tooling.

## Goal

Remove the temporary SQLite importer after it has served its purpose while
preserving the PostgreSQL contract history.

## Plan

- [ ] Remove `legacy-import/`, its dependencies, and its commands.
- [ ] Keep a historical record of the completed transfer in the runbook or
      release notes.
- [ ] Do not remove SQL migrations, `schema.sql`, or migration policy.

## Definition of done

Permanent infra contains only the PostgreSQL contract and does not depend on the
SQLite/Python importer.
