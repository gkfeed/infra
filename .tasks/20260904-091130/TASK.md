# I11A — Clean up bootstrap-only agent instructions

- STATUS: DONE
- PRIORITY: 2
- DEPENDS: [I11](../20260904-0911/TASK.md)

## Goal

After the initial repository setup and rehearsal are complete, reduce
`AGENTS.md` to the instructions that remain useful for normal schema ownership
and migration work.

## Plan

- [x] Audit every `AGENTS.md` rule after the I11 rehearsal.
- [x] Remove or rewrite task-roadmap and repository-bootstrap instructions that
      no longer apply.
- [x] Retain enduring schema ownership, migration safety, application boundary,
      privilege, and secret-handling rules.
- [x] Keep the detailed migration policy in `docs/migrations.md`; avoid copying
      procedural detail into `AGENTS.md` when a concise invariant is enough.
- [x] Keep temporary importer guidance only while the importer still exists.
- [x] Do not change migrations, schema objects, privileges, importer code, or
      application code in this task.

## Definition of done

A new agent sees only actionable, current repository instructions in
`AGENTS.md`, while permanent safety rules and links to detailed policy remain.

## Validation

Audited every rule after the I11 rehearsal. Removed the bootstrap task-roadmap
workflow, retained the repository and application boundaries, and made the
least-privilege role rules explicit. Detailed migration and role procedures
remain in `docs/migrations.md` and `docs/application-roles.md`. The temporary
importer guidance remains while `legacy-import/` exists. `git diff --check` and
`make help` passed. No migration, schema, privilege, importer, or application
code changed.
