#!/bin/sh
set -eu
umask 077

SOURCE_ENV=${SOURCE_ENV:-.env.rehearsal-source}
RESTORE_ENV=${RESTORE_ENV:-.env.rehearsal-restore}
SOURCE_PROJECT=gkfeed-transfer-source
RESTORE_PROJECT=gkfeed-transfer-restore
COMPOSE_FILES="-f compose.yaml -f compose.rehearsal.yaml"

if [ "$#" -ne 2 ]; then
    echo "usage: $0 /private/path/source.sqlite /private/path/gkfeed-data.dump" >&2
    exit 2
fi

source_sqlite=$(realpath "$1")
dump_path=$2
SOURCE_ENV=$(realpath "$SOURCE_ENV")
RESTORE_ENV=$(realpath "$RESTORE_ENV")

for env_file in "$SOURCE_ENV" "$RESTORE_ENV"; do
    if [ ! -f "$env_file" ]; then
        echo "missing rehearsal environment: $env_file" >&2
        exit 2
    fi
    mode=$(stat -c %a "$env_file")
    if [ "$mode" != 600 ]; then
        echo "$env_file must have mode 0600, found $mode" >&2
        exit 2
    fi
done

if [ ! -f "$source_sqlite" ]; then
    echo "SQLite snapshot does not exist: $source_sqlite" >&2
    exit 2
fi

read_env() {
    env_file=$1
    key=$2
    (
        set -a
        # These are private files created from the repository examples.
        # shellcheck disable=SC1090
        . "$env_file"
        eval "value=\${$key:-}"
        if [ -z "$value" ]; then
            echo "missing $key in $env_file" >&2
            exit 2
        fi
        printf '%s' "$value"
    )
}

compose() {
    project=$1
    env_file=$2
    shift 2
    (
        set -a
        # shellcheck disable=SC1090
        . "$env_file"
        docker compose --project-name "$project" --env-file "$env_file" \
            $COMPOSE_FILES "$@"
    )
}

source_url=$(read_env "$SOURCE_ENV" DATABASE_URL)
restore_url=$(read_env "$RESTORE_ENV" DATABASE_URL)
api_password=$(read_env "$RESTORE_ENV" API_LOGIN_PASSWORD)
parser_password=$(read_env "$RESTORE_ENV" PARSER_LOGIN_PASSWORD)

if [ "$(sqlite3 -readonly "$source_sqlite" 'PRAGMA integrity_check;')" != ok ]; then
    echo "SQLite integrity_check did not return ok" >&2
    exit 1
fi

evidence_dir=$(dirname "$dump_path")/rehearsal-evidence
install -d -m 0700 "$evidence_dir"
sha256sum "$source_sqlite" > "$evidence_dir/sqlite-before.sha256"

compose "$SOURCE_PROJECT" "$SOURCE_ENV" up -d --wait postgres
compose "$RESTORE_PROJECT" "$RESTORE_ENV" up -d --wait postgres

DATABASE_URL=$source_url make migrate
DATABASE_URL=$restore_url make migrate

if [ ! -x legacy-import/.venv/bin/python ]; then
    echo "install the importer first: python3 -m venv legacy-import/.venv" >&2
    echo "then run: legacy-import/.venv/bin/pip install -r legacy-import/requirements.txt" >&2
    exit 2
fi

LEGACY_SQLITE_PATH=$source_sqlite DATABASE_URL=$source_url \
    legacy-import/.venv/bin/python legacy-import/importer.py --dry-run \
    > "$evidence_dir/dry-run.json"

jq -e '
    .mode == "dry-run"
    and (.target | all(.[]; .rows == 0))
    and .source.passwords.malformed_or_unsupported == 0
' "$evidence_dir/dry-run.json" >/dev/null

LEGACY_SQLITE_PATH=$source_sqlite DATABASE_URL=$source_url \
    legacy-import/.venv/bin/python legacy-import/importer.py --execute \
    > "$evidence_dir/execute.json"

jq -e '
    .mode == "execute"
    and .transaction == "committed"
    and (.target_before | all(.[]; .rows == 0))
    and (.identity_sequences | all(.[]; .verified == true))
' "$evidence_dir/execute.json" >/dev/null

jq -S '.source.reconciliation | map_values(.expected_target_count)' \
    "$evidence_dir/dry-run.json" > "$evidence_dir/expected-counts.json"
jq -S '.target_after' "$evidence_dir/execute.json" \
    > "$evidence_dir/actual-counts.json"
diff -u "$evidence_dir/expected-counts.json" "$evidence_dir/actual-counts.json"

jq -S '.source.tombstones' "$evidence_dir/dry-run.json" \
    > "$evidence_dir/expected-tombstones.json"
jq -S '.source.tombstones' "$evidence_dir/execute.json" \
    > "$evidence_dir/actual-tombstones.json"
diff -u "$evidence_dir/expected-tombstones.json" "$evidence_dir/actual-tombstones.json"

DATABASE_URL=$source_url scripts/export-data-dump.sh "$dump_path"
DATABASE_URL=$source_url scripts/database-manifest.sh "$evidence_dir/source.manifest"
DATABASE_URL=$restore_url scripts/restore-data-dump.sh "$dump_path"
DATABASE_URL=$restore_url scripts/database-manifest.sh "$evidence_dir/restore.manifest"
diff -u "$evidence_dir/source.manifest" "$evidence_dir/restore.manifest"

docker run --rm --network=host -i \
    -e API_LOGIN_PASSWORD="$api_password" \
    -e PARSER_LOGIN_PASSWORD="$parser_password" \
    postgres:17.10-bookworm \
    psql "$restore_url" -X -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gkfeed_api_login') THEN
        CREATE ROLE gkfeed_api_login LOGIN INHERIT IN ROLE gkfeed_api;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gkfeed_parser_login') THEN
        CREATE ROLE gkfeed_parser_login LOGIN INHERIT IN ROLE gkfeed_parser;
    END IF;
END
$$;
\getenv api_password API_LOGIN_PASSWORD
\getenv parser_password PARSER_LOGIN_PASSWORD
SELECT format('ALTER ROLE gkfeed_api_login NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L', :'api_password') \gexec
SELECT format('ALTER ROLE gkfeed_parser_login NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L', :'parser_password') \gexec
SQL

sha256sum "$source_sqlite" > "$evidence_dir/sqlite-after.sha256"
diff -u "$evidence_dir/sqlite-before.sha256" "$evidence_dir/sqlite-after.sha256"
chmod 0400 "$evidence_dir"/*

compose "$SOURCE_PROJECT" "$SOURCE_ENV" stop postgres

echo "Database rehearsal passed."
echo "The restored PostgreSQL instance remains running under project $RESTORE_PROJECT."
echo "Use DATABASE_URL from $RESTORE_ENV for operator checks."
echo "Use the gkfeed_api_login and gkfeed_parser_login URLs documented in docs/container-postgres.md."
