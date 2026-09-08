# I11B: Fix the execute-report runbook gate

- STATUS: DONE
- PRIORITY: 1
- DEPENDS: [I11](../20260904-0911/TASK.md)

## Goal

Make the manual cutover runbook validate the current importer execute-report
shape.

## Plan

- [x] Change the step 9 `target_before` check to inspect each table's `rows`
      field.
- [x] Change the identity-sequence check to inspect each sequence's `verified`
      field.
- [x] Run both corrected expressions against a representative successful
      execute report and confirm that they reject a failing value.
- [x] Do not change importer, migration, schema, privilege, or application
      code.

## Definition of done

The documented step 9 gate returns true for a successful current execute
report and false when a target row count is nonzero or a sequence probe is not
verified.

## Validation

The complete step 9 `jq -e` gate returned true for the committed execute report
from a production-sized rehearsal using the current structured `target_before`
and `identity_sequences` entries. It returned false after changing one table's
`rows` value to 1, and returned false after changing one sequence's `verified`
value to false.
