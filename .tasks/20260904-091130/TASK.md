# I11A — Clean up bootstrap-only agent instructions

- STATUS: PENDING
- PRIORITY: 2
- DEPENDS: [I11](../20260904-0911/TASK.md)

## Goal

After the initial repository setup and rehearsal are complete, reduce
`AGENTS.md` to the instructions that remain useful for normal schema ownership
and migration work.

## Plan

- [ ] Audit every `AGENTS.md` rule after the I11 rehearsal.
- [ ] Remove or rewrite task-roadmap and repository-bootstrap instructions that
      no longer apply.
- [ ] Retain enduring schema ownership, migration safety, application boundary,
      privilege, and secret-handling rules.
- [ ] Keep the detailed migration policy in `docs/migrations.md`; avoid copying
      procedural detail into `AGENTS.md` when a concise invariant is enough.
- [ ] Keep temporary importer guidance only while the importer still exists.
- [ ] Do not change migrations, schema objects, privileges, importer code, or
      application code in this task.

## Definition of done

A new agent sees only actionable, current repository instructions in
`AGENTS.md`, while permanent safety rules and links to detailed policy remain.
