# I11B: Fix the execute-report runbook gate

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [I11](../20260904-0911/TASK.md)

## Goal

Make the manual cutover runbook validate the current importer execute-report
shape.

## Plan

- [ ] Change the step 9 `target_before` check to inspect each table's `rows`
      field.
- [ ] Change the identity-sequence check to inspect each sequence's `verified`
      field.
- [ ] Run both corrected expressions against a representative successful
      execute report and confirm that they reject a failing value.
- [ ] Do not change importer, migration, schema, privilege, or application
      code.

## Definition of done

The documented step 9 gate returns true for a successful current execute
report and false when a target row count is nonzero or a sequence probe is not
verified.
