# Orphan item analysis

This temporary tool exports legacy SQLite items whose `feed_id` has no matching
`feed`. It never changes SQLite and never connects to PostgreSQL.

Run it against a restored SQLite snapshot:

```sh
LEGACY_SQLITE_PATH=/private/path/snapshot.sqlite \
  legacy-import/.venv/bin/python \
  legacy-import/orphan-item-analysis/export.py
```

The command creates a timestamped directory under `private-output/` with mode
`0700`. Point a local analysis agent at that generated directory, not at the
production dump itself.

- `summary.json` contains counts only.
- `orphan_items.jsonl` contains the full legacy item fields, missing feed ID,
  tombstone row count, and distinct tombstone user IDs.

Both files have mode `0600` and contain production-derived information. The
output directory is ignored by Git. Do not paste its contents into issues,
commits, logs, or ordinary reports. Delete the generated directory after the
analysis decision is recorded.
