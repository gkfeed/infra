# Item feed index

Migration `20261103072958` adds a non-unique B-tree on `item(feed_id)` for
feed-scoped item lookups and feed deletion cascades. The parser's fallback
identity remains `(feed_id, title, link, text)`; date is excluded and duplicate
identities remain allowed. The index does not contain arbitrary text, which can
exceed PostgreSQL's B-tree entry limit. The existing unique
`item_hash(feed_id, hash)` index already covers hash lookups.

## Measurement

On disposable PostgreSQL 17.10 with the canonical schema, a synthetic fixture
held 210,100 items with roughly 200-byte bodies: feeds of 100, 10,000, 100,000,
and 100,000 items, inserted in feed order. This distribution is an assumption,
not a production measurement. After `VACUUM ANALYZE`, each lookup used the
parser PR #104 query shape: `feed_id = ?` and `(title, link, text) IN (VALUES
...)` with 250 distinct candidates. The table shows medians of three
`EXPLAIN (ANALYZE, BUFFERS)` executions. Hits match up to 250 rows; misses
match none. Results depend on hardware, cache, statistics and row distribution.

| Feed rows | Candidates | Before, ms | After, ms | Before plan | After plan |
| ---: | --- | ---: | ---: | --- | --- |
| 100 | hits | 10.28 | 0.16 | parallel seq scan | index scan |
| 100 | misses | 10.02 | 0.15 | parallel seq scan | index scan |
| 10,000 | hits | 11.19 | 2.44 | parallel seq scan | index scan |
| 10,000 | misses | 10.92 | 2.21 | parallel seq scan | index scan |
| 100,000 | hits | 15.87 | 23.23 | parallel seq scan | index scan |
| 100,000 | misses | 15.46 | 22.13 | parallel seq scan | index scan |

For the 10,000-row feed the final execution touched 7,782 shared buffers
before and 382 after; these counts include hits and reads and are not distinct
physical disk reads. The index occupied 1.5 MiB after the insertion experiment.
Three rolled-back 5,000-row inserts, including the existing item-change
triggers, had medians of 62.00 ms and 64.66 ms before and after; reported WAL
for the insert plan rose from about 1.94 MB to 2.26 MB. These short local runs
are illustrative, not a throughput guarantee. Index maintenance also costs
space and work on deletes and updates of `feed_id`.

The 100,000-row case regressed because PostgreSQL selected a serial index scan
instead of the parallel table scan. Before applying in production, the operator
should inspect feed sizes and plans on representative data. Keep planner
statistics current and investigate large-feed regressions; this index does not
guarantee a faster plan for every distribution.

## Rollout

The migration uses dbmate's default transaction and ordinary `CREATE INDEX`.
PostgreSQL scans the full table and holds a lock that blocks item writes for the
duration of the build and until the transaction commits; reads continue. A
waiting DDL lock can also queue later writes. The operator should choose a
maintenance window, account for index disk space and build time, and monitor
locks. Test the build against a production-sized disposable restore before
scheduling. Do not run unmerged migrations on shared databases. If the index
must be removed, use a new reviewed forward migration rather than editing this
migration or the registry.
