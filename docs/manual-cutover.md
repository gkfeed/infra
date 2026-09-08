# Manual SQLite-to-PostgreSQL cutover

This runbook moves production data once. A designated operator performs each
step. This repository does not deploy applications or store application
passwords.

Use a private shell with history disabled or a secret manager for connection
URLs. Do not put connection URLs, passwords, the SQLite snapshot, or importer
reports in Git. The importer report contains production-derived feed ID
mappings.

## Before the maintenance window

1. Record the application releases, deployment commands, live SQLite path,
   maintenance window, and operators in the change record.

   The API release must contain storage commit `f6520e6`. The parser release
   must contain compatibility-check commit `03c7a11`. Verify both candidate
   revisions from clean application checkouts:

   ```sh
   git merge-base --is-ancestor f6520e6 "$API_RELEASE"
   git merge-base --is-ancestor 03c7a11 "$PARSER_RELEASE"
   ```

   Both commands must exit zero. Keep the API library storage-seam PostgreSQL
   change unmerged and undeployed at this stage. Merge and deploy it only after
   the schema, grants, import, reconciliation, sequence checks, and staging
   cleanup below have passed. It is not a SQLite production transition
   release.

2. Create a private evidence directory and install the isolated importer:

   ```sh
   export CUTOVER_DIR=/secure/path/gkfeed-cutover
   umask 077
   install -d -m 0700 "$CUTOVER_DIR"
   python3 -m venv legacy-import/.venv
   legacy-import/.venv/bin/pip install -r legacy-import/requirements.txt
   ```

3. Prepare a new, empty PostgreSQL database. Set `DATABASE_URL` to an operator
   connection that owns the domain objects, can create roles, and meets the
   importer requirements in `legacy-import/README.md`. Apply only merged infra
   migrations with the pinned dbmate:

   ```sh
   make status
   make migrate
   make status
   ```

   The final status must show migrations `20260904184133` and `20260905082946`
   as applied and no pending migration. Confirm the registry and empty target:

   ```sh
   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 <<'SQL'
   SELECT version
   FROM public.schema_migrations
   WHERE version IN ('20260904184133', '20260905082946')
   ORDER BY version;

   SELECT 'users' AS table_name, count(*) FROM public.users
   UNION ALL SELECT 'feed', count(*) FROM public.feed
   UNION ALL SELECT 'item', count(*) FROM public.item
   UNION ALL SELECT 'feed_parser', count(*) FROM public.feed_parser
   UNION ALL SELECT 'item_hash', count(*) FROM public.item_hash
   UNION ALL SELECT 'webauthn_credentials', count(*) FROM public.webauthn_credentials
   UNION ALL SELECT 'refresh_tokens', count(*) FROM public.refresh_tokens
   ORDER BY table_name;
   SQL
   ```

   The first query must return both IDs. Every count must be zero.

4. Create LOGIN roles outside Git. Replace the example names with the names in
   the deployment secret inventory. `\password` prompts without putting the
   password in shell history:

   ```sh
   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1
   CREATE ROLE gkfeed_api_login LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS IN ROLE gkfeed_api;
   \password gkfeed_api_login
   CREATE ROLE gkfeed_parser_login LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS IN ROLE gkfeed_parser;
   \password gkfeed_parser_login
   \q
   ```

   Store both application URLs in the deployment secret manager. Confirm that
   each login has only its intended group, no elevated attributes, and owns no
   database object:

   ```sh
   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 <<'SQL'
   SELECT member.rolname AS login, parent.rolname AS member_of
   FROM pg_auth_members membership
   JOIN pg_roles parent ON parent.oid = membership.roleid
   JOIN pg_roles member ON member.oid = membership.member
   WHERE member.rolname IN ('gkfeed_api_login', 'gkfeed_parser_login')
   ORDER BY member.rolname, parent.rolname;

   SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication,
          rolbypassrls
   FROM pg_roles
   WHERE rolname IN ('gkfeed_api_login', 'gkfeed_parser_login')
   ORDER BY rolname;

   WITH application_logins AS (
       SELECT oid FROM pg_roles
       WHERE rolname IN ('gkfeed_api_login', 'gkfeed_parser_login')
   )
   SELECT 'database' AS object_type, count(*) AS owned_objects
   FROM pg_database WHERE datdba IN (SELECT oid FROM application_logins)
   UNION ALL
   SELECT 'schema', count(*)
   FROM pg_namespace WHERE nspowner IN (SELECT oid FROM application_logins)
   UNION ALL
   SELECT 'relation', count(*)
   FROM pg_class WHERE relowner IN (SELECT oid FROM application_logins)
   ORDER BY object_type;
   SQL
   ```

   The membership query must show one matching group per login. Every elevated
   attribute must be false and every `owned_objects` count must be zero.

   Confirm that both application groups can read their contract and migration
   registry. This uses the operator connection only to assume each group:

   ```sh
   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 <<'SQL'
   SET ROLE gkfeed_api;
   SELECT (SELECT count(*) FROM public.schema_migrations),
          (SELECT count(*) FROM public.users),
          (SELECT count(*) FROM public.feed),
          (SELECT count(*) FROM public.item),
          (SELECT count(*) FROM public.webauthn_credentials),
          (SELECT count(*) FROM public.refresh_tokens);
   RESET ROLE;
   SET ROLE gkfeed_parser;
   SELECT (SELECT count(*) FROM public.schema_migrations),
          (SELECT count(*) FROM public.feed),
          (SELECT count(*) FROM public.item),
          (SELECT count(*) FROM public.feed_parser),
          (SELECT count(*) FROM public.item_hash);
   SQL
   ```

   The command must exit zero. The complete allowed and forbidden operation
   checks remain the disposable-database checks in `docs/application-roles.md`.

## Stop SQLite and take the final snapshot

5. Start the maintenance window. Run the API and parser stop commands recorded
   in the change record. The process supervisor must show every API, parser
   dispatcher, and parser worker instance as stopped. Check the live files:

   ```sh
   lsof "$LIVE_SQLITE" "$LIVE_SQLITE-wal" "$LIVE_SQLITE-shm" 2>/dev/null
   ```

   This must print no process. Do not continue if any SQLite writer can restart
   automatically.

6. Make the cutover copy only after all writers have stopped:

   ```sh
   export SNAPSHOT="$CUTOVER_DIR/gkfeed-cutover.sqlite"
   sqlite3 "$LIVE_SQLITE" ".backup '$SNAPSHOT'"
   sqlite3 "$SNAPSHOT" 'PRAGMA integrity_check;'
   sha256sum "$SNAPSHOT" | tee "$CUTOVER_DIR/sqlite.sha256"
   chmod 0400 "$SNAPSHOT" "$CUTOVER_DIR/sqlite.sha256"
   ```

   `integrity_check` must print exactly `ok`. Record the checksum in the private
   change evidence. Keep the live database and snapshot unchanged.

## Inspect and import

7. Point the importer at the final snapshot and clean target. Run a fresh
   dry-run and retain its private report:

   ```sh
   export LEGACY_SQLITE_PATH="$SNAPSHOT"
   legacy-import/.venv/bin/python legacy-import/importer.py --dry-run \
     > "$CUTOVER_DIR/dry-run.json"
   chmod 0600 "$CUTOVER_DIR/dry-run.json"
   jq -e '
     .mode == "dry-run"
     and (.target | all(.[]; .rows == 0))
     and .source.passwords.malformed_or_unsupported == 0
   ' "$CUTOVER_DIR/dry-run.json"
   jq '{reconciliation: .source.reconciliation,
        tombstones: .source.tombstones,
        feed_normalization: .source.feed_normalization,
        feed_parser_normalization: .source.feed_parser_normalization,
        item_hash_normalization: .source.item_hash_normalization,
        passwords: .source.passwords}' "$CUTOVER_DIR/dry-run.json"
   ```

   The first `jq` command must print `true` and exit zero. Review each aggregate
   with the owner. Stop on an unexplained removal, merge, password category, or
   tombstone count.

8. **Point of no return.** The next command begins PostgreSQL writes. After it
   starts, switching production back to SQLite is forbidden, even if a later
   cutover step fails. Keep applications stopped and repair or recreate the
   PostgreSQL target before continuing.

   Run the importer once:

   ```sh
   legacy-import/.venv/bin/python legacy-import/importer.py --execute \
     > "$CUTOVER_DIR/execute.json"
   chmod 0600 "$CUTOVER_DIR/execute.json"
   ```

9. Verify the commit, counts, tombstones, and identity sequence probes:

   ```sh
   jq -e '
     .mode == "execute"
     and .transaction == "committed"
     and (.target_before | all(.[]; .rows == 0))
     and (.identity_sequences | all(.[]; .verified == true))
   ' "$CUTOVER_DIR/execute.json"

   jq -S '.source.reconciliation | map_values(.expected_target_count)' \
     "$CUTOVER_DIR/dry-run.json" > "$CUTOVER_DIR/expected-counts.json"
   jq -S '.target_after' "$CUTOVER_DIR/execute.json" \
     > "$CUTOVER_DIR/actual-counts.json"
   diff -u "$CUTOVER_DIR/expected-counts.json" "$CUTOVER_DIR/actual-counts.json"

   jq -S '.source.tombstones' "$CUTOVER_DIR/dry-run.json" \
     > "$CUTOVER_DIR/expected-tombstones.json"
   jq -S '.source.tombstones' "$CUTOVER_DIR/execute.json" \
     > "$CUTOVER_DIR/actual-tombstones.json"
   diff -u "$CUTOVER_DIR/expected-tombstones.json" "$CUTOVER_DIR/actual-tombstones.json"
   jq '{tombstones: .source.tombstones,
        deleted_distinct_items: .deleted_distinct_items,
        identity_sequences: .identity_sequences}' "$CUTOVER_DIR/execute.json"
   ```

   The first command must print `true`. Both diffs must produce no output and
   exit zero. Record the displayed tombstone counts and distinct tombstoned-item
   count in the private evidence.

10. Confirm target counts and staging cleanup:

   ```sh
   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 <<'SQL'
   SELECT 'users' AS table_name, count(*) FROM public.users
   UNION ALL SELECT 'feed', count(*) FROM public.feed
   UNION ALL SELECT 'item', count(*) FROM public.item
   UNION ALL SELECT 'feed_parser', count(*) FROM public.feed_parser
   UNION ALL SELECT 'item_hash', count(*) FROM public.item_hash
   UNION ALL SELECT 'webauthn_credentials', count(*) FROM public.webauthn_credentials
   UNION ALL SELECT 'refresh_tokens', count(*) FROM public.refresh_tokens
   ORDER BY table_name;

   SELECT NOT EXISTS (
       SELECT 1
       FROM pg_catalog.pg_class relation
       JOIN pg_catalog.pg_namespace namespace ON namespace.oid = relation.relnamespace
       WHERE relation.relname = 'legacy_valid_tombstoned_items'
   ) AS staging_absent;
   SQL
   ```

   The counts must equal `actual-counts.json`. `staging_absent` must be true.
   Do not deploy either application until both checks pass.

## Switch applications

11. Merge the approved API storage-seam change only now. Verify that the merged
   production revision contains commit `f6520e6`, then run the API deployment
   command recorded in the change record:

   ```sh
   git merge-base --is-ancestor f6520e6 "$API_PRODUCTION_RELEASE"
   ```

   This must exit zero. Set `GKFEED_DATABASE_URL` to the API LOGIN URL, not the
   operator URL. The API startup check must succeed before it listens. Confirm
   the health endpoint or one authenticated read request and check the logs for
   schema-readiness errors. Never run an API version that writes SQLite again.

12. Configure the parser release with the parser LOGIN URL in `DB_URL`. Before
   starting any dispatcher or worker, run its read-only version check from the
   parser checkout:

   ```sh
   DB_URL="$PARSER_DATABASE_URL" \
     .venv/bin/python -m app.run.check_schema_compatibility
   ```

   It must print `Database schema is ready for the parser.` and exit zero. Only
   then run the parser deployment command from the change record. The process
   supervisor must show the dispatcher and both worker types as running. Check
   their first database operations for permission or schema errors.

13. End the window after an API read and a parser-created item both succeed
   against PostgreSQL. Preserve the SQLite source, checksum, private reports,
   deployed revisions, aggregate counts, and operator sign-off under the
   production retention policy. Do not commit them here.
