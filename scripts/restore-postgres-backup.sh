#!/bin/sh
set -eu
umask 077

POSTGRES_CLIENT_IMAGE=postgres:17.10-bookworm

: "${DATABASE_URL:?set DATABASE_URL to the migrated empty target}"

if [ "$#" -ne 1 ]; then
	echo "usage: DATABASE_URL=... $0 /download/path/gkfeed-*.manifest" >&2
	exit 2
fi

manifest=$(realpath "$1")
if [ ! -f "$manifest" ]; then
	echo "backup manifest does not exist: $manifest" >&2
	exit 2
fi
manifest_dir=$(dirname "$manifest")

manifest_value() {
	key=$1
	awk -F '\t' -v key="$key" '
        $1 == key { count++; value = $2 }
        END {
            if (count != 1) exit 1
            print value
        }
    ' "$manifest"
}

format=$(manifest_value format)
if [ "$format" != gkfeed-postgres-backup-v1 ]; then
	echo "unsupported backup manifest format: $format" >&2
	exit 2
fi

dump_name=$(manifest_value dump_name)
dump_bytes=$(manifest_value dump_bytes)
dump_sha256=$(manifest_value dump_sha256)
migration_version=$(manifest_value migration_version)

case "$dump_name" in
'' | */* | .*)
	echo "unsafe dump name in manifest" >&2
	exit 2
	;;
esac
case "$dump_bytes" in
*[!0-9]* | '')
	echo "invalid dump size in manifest" >&2
	exit 2
	;;
esac
case "$dump_sha256" in
*[!0-9a-f]* | '')
	echo "invalid dump checksum in manifest" >&2
	exit 2
	;;
esac
if [ "${#dump_sha256}" -ne 64 ]; then
	echo "invalid dump checksum length in manifest" >&2
	exit 2
fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/gkfeed-restore.XXXXXX")
cleanup() {
	case "$work_dir" in
	"${TMPDIR:-/tmp}"/gkfeed-restore.*) rm -rf -- "$work_dir" ;;
	esac
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

payload_rows=$work_dir/payloads.tsv
awk -F '\t' '$1 == "payload" { print $2 "\t" $3 "\t" $4 }' \
	"$manifest" >"$payload_rows"
if [ ! -s "$payload_rows" ]; then
	echo "manifest contains no payloads" >&2
	exit 2
fi

payload_count=0
while IFS="$(printf '\t')" read -r payload_name expected_bytes expected_sha256; do
	case "$payload_name" in
	'' | */* | .*)
		echo "unsafe payload name in manifest" >&2
		exit 2
		;;
	esac
	payload=$manifest_dir/$payload_name
	if [ ! -f "$payload" ]; then
		echo "missing payload: $payload" >&2
		exit 2
	fi
	actual_bytes=$(wc -c <"$payload" | tr -d ' ')
	actual_sha256=$(sha256sum "$payload" | awk '{ print $1 }')
	if [ "$actual_bytes" != "$expected_bytes" ]; then
		echo "payload size mismatch: $payload_name" >&2
		exit 1
	fi
	if [ "$actual_sha256" != "$expected_sha256" ]; then
		echo "payload checksum mismatch: $payload_name" >&2
		exit 1
	fi
	payload_count=$((payload_count + 1))
done <"$payload_rows"

first_payload=$(awk -F '\t' 'NR == 1 { print $1 }' "$payload_rows")
if [ "$payload_count" -eq 1 ] && [ "$first_payload" = "$dump_name" ]; then
	dump_path=$manifest_dir/$dump_name
else
	dump_path=$work_dir/$dump_name
	: >"$dump_path"
	while IFS="$(printf '\t')" read -r payload_name _expected_bytes _expected_sha256; do
		cat -- "$manifest_dir/$payload_name" >>"$dump_path"
	done <"$payload_rows"
fi

actual_dump_bytes=$(wc -c <"$dump_path" | tr -d ' ')
actual_dump_sha256=$(sha256sum "$dump_path" | awk '{ print $1 }')
if [ "$actual_dump_bytes" != "$dump_bytes" ]; then
	echo "reassembled dump size does not match the manifest" >&2
	exit 1
fi
if [ "$actual_dump_sha256" != "$dump_sha256" ]; then
	echo "reassembled dump checksum does not match the manifest" >&2
	exit 1
fi

dump_dir=$(dirname "$dump_path")
dump_file=$(basename "$dump_path")
toc=$work_dir/archive.toc
restore_toc=$work_dir/restore.toc

docker run --rm --user "$(id -u):$(id -g)" \
	-v "$dump_dir:/input:ro" \
	"$POSTGRES_CLIENT_IMAGE" \
	pg_restore --list "/input/$dump_file" >"$toc"

# The target already records migrations applied from this repository.
# Restore domain tables in foreign-key order and leave the registry unchanged.
expected_tables='public.feed
public.feed_parser
public.item
public.item_hash
public.refresh_tokens
public.users
public.webauthn_credentials'
archive_tables=$(awk '
    $4 == "TABLE" && $5 == "DATA" && !($6 == "public" && $7 == "schema_migrations") {
        print $6 "." $7
    }
' "$toc" | sort)
if [ "$archive_tables" != "$expected_tables" ]; then
	echo "archive domain tables do not match this restore script" >&2
	printf 'expected:\n%s\nactual:\n%s\n' "$expected_tables" "$archive_tables" >&2
	exit 1
fi

: >"$restore_toc"
for table_name in users feed item feed_parser item_hash webauthn_credentials refresh_tokens; do
	awk -v table_name="$table_name" '
        $4 == "TABLE" && $5 == "DATA" && $6 == "public" && $7 == table_name
    ' "$toc" >>"$restore_toc"
done
awk '$4 == "SEQUENCE" && $5 == "SET" { print }' "$toc" >>"$restore_toc"

export DATABASE_URL
target_version=$(docker run --rm --network=host -e DATABASE_URL \
	"$POSTGRES_CLIENT_IMAGE" \
	sh -ceu 'exec psql "$DATABASE_URL" -X -qAt -v ON_ERROR_STOP=1 \
        -c "SELECT max(version) FROM public.schema_migrations;"')
if [ "$target_version" != "$migration_version" ]; then
	echo "target migration $target_version does not match backup migration $migration_version" >&2
	exit 1
fi

docker run --rm --interactive --network=host -e DATABASE_URL \
	"$POSTGRES_CLIENT_IMAGE" \
	sh -ceu 'exec psql "$DATABASE_URL" -X -q -v ON_ERROR_STOP=1' <<'SQL'
DO $$
DECLARE
    relation record;
    populated boolean;
BEGIN
    FOR relation IN
        SELECT namespace.nspname AS schema_name, class.relname AS table_name
        FROM pg_catalog.pg_class class
        JOIN pg_catalog.pg_namespace namespace ON namespace.oid = class.relnamespace
        WHERE class.relkind IN ('r', 'p')
          AND namespace.nspname NOT IN ('pg_catalog', 'information_schema')
          AND namespace.nspname !~ '^pg_toast'
          AND NOT (namespace.nspname = 'public' AND class.relname = 'schema_migrations')
    LOOP
        EXECUTE format(
            'SELECT EXISTS (SELECT FROM %I.%I LIMIT 1)',
            relation.schema_name,
            relation.table_name
        ) INTO populated;
        IF populated THEN
            RAISE EXCEPTION 'restore target table %.% is not empty',
                relation.schema_name, relation.table_name;
        END IF;
    END LOOP;
END
$$;
SQL

docker run --rm --network=host -e DATABASE_URL \
	-e DUMP_FILE="$dump_file" \
	-v "$dump_dir:/input:ro" \
	-v "$work_dir:/work:ro" \
	"$POSTGRES_CLIENT_IMAGE" \
	sh -ceu 'exec pg_restore \
        --dbname="$DATABASE_URL" \
        --data-only \
        --no-owner \
        --no-privileges \
        --exit-on-error \
        --single-transaction \
        --use-list=/work/restore.toc \
        "/input/$DUMP_FILE"'

docker run --rm --interactive --network=host -e DATABASE_URL \
	"$POSTGRES_CLIENT_IMAGE" \
	sh -ceu 'exec psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1' <<'SQL'
SELECT 'users' AS table_name, count(*) AS rows FROM public.users
UNION ALL SELECT 'feed', count(*) FROM public.feed
UNION ALL SELECT 'item', count(*) FROM public.item
UNION ALL SELECT 'feed_parser', count(*) FROM public.feed_parser
UNION ALL SELECT 'item_hash', count(*) FROM public.item_hash
UNION ALL SELECT 'webauthn_credentials', count(*) FROM public.webauthn_credentials
UNION ALL SELECT 'refresh_tokens', count(*) FROM public.refresh_tokens;
SQL

echo "Restored and verified $manifest"
