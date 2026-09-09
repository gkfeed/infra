# I14: Add production backup and restore operations

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [I13](../20260908-150926/TASK.md)

## Goal

Add tested, monitored backups for the PostgreSQL container after the one-time
cutover workflow is accepted.

## Plan

- [ ] Agree on RPO, schedule, retention, and restore-test cadence.
- [ ] Choose an encrypted off-host destination and a separate backup
      credential.
- [ ] Create PostgreSQL 17 logical custom dumps with checksums in a private
      host directory.
- [ ] Automate retention without deleting the last known-good backup.
- [ ] Alert the operator when creation, upload, verification, or retention
      fails.
- [ ] Restore a backup into a clean disposable cluster on a fixed schedule.
- [ ] Document disaster recovery and record measured restore time.

## Definition of done

A scheduled backup reaches off-host storage, failures notify the operator, and
a clean restore test proves the documented recovery procedure.

## Validation

Complete after I13 and before treating the container as a backed-up production
service.
