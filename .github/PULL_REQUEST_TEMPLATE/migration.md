## Migration compatibility

- Migration ID:
- Change phase: compatible / expand / migrate / contract
- Affected contracts and applications:
- Minimum migration ID required by each affected application after this change:
- Compatible application releases before this change:
- Mixed-version behavior during deployment:
- Backfill plan and completion check, or `none`:
- Compatibility period start, or `not applicable`:
- Compatibility period end condition and earliest contract milestone, or `not applicable`:
- Contract-phase evidence, or `not applicable`:
- Lock and runtime impact:
- Grant changes, or `none`:

For a shared-column rename or removal, identify the earlier expand migration.
Keep the old column until every named application release is deployed, required
backfills are complete, and the recorded compatibility period has ended.
