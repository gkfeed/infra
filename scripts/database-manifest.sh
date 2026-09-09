#!/bin/bash
set -euo pipefail

POSTGRES_CLIENT_IMAGE=postgres:17.10-bookworm

: "${DATABASE_URL:?set DATABASE_URL}"

if [ "$#" -gt 1 ]; then
    echo "usage: DATABASE_URL=... $0 [manifest-file]" >&2
    exit 2
fi

output=${1:-/dev/stdout}
case "$output" in
    /dev/stdout) ;;
    *)
        if [ -e "$output" ]; then
            echo "refusing to overwrite manifest: $output" >&2
            exit 2
        fi
        umask 077
        install -d -m 0700 "$(dirname "$output")"
        ;;
esac

psql_value() {
    docker run --rm --network=host -e DATABASE_URL \
        "$POSTGRES_CLIENT_IMAGE" \
        psql "$DATABASE_URL" -X -qAt -v ON_ERROR_STOP=1 -c "$1"
}

hash_table() {
    table=$1
    order_column=$2
    count=$(psql_value "SELECT count(*) FROM public.$table;")
    hash=$(docker run --rm --network=host -e DATABASE_URL \
        "$POSTGRES_CLIENT_IMAGE" \
        psql "$DATABASE_URL" -X -q -v ON_ERROR_STOP=1 \
            -c "COPY (SELECT * FROM public.$table ORDER BY $order_column) TO STDOUT (FORMAT binary);" \
        | sha256sum | awk '{print $1}')
    printf 'table\t%s\t%s\t%s\n' "$table" "$count" "$hash"
}

write_manifest() {
    migration_count=$(psql_value "
        SELECT count(*) FROM public.schema_migrations
        WHERE version IN ('20260904184133', '20260905082946');")
    if [ "$migration_count" != 2 ]; then
        echo "required migrations are missing" >&2
        exit 1
    fi

    staging_absent=$(psql_value "
        SELECT NOT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_class relation
            JOIN pg_catalog.pg_namespace namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public'
              AND relation.relname = 'legacy_valid_tombstoned_items'
        );")
    if [ "$staging_absent" != t ]; then
        echo "temporary importer staging table still exists" >&2
        exit 1
    fi

    hash_table users id
    hash_table feed id
    hash_table item id
    hash_table feed_parser feed_id
    hash_table item_hash id
    hash_table webauthn_credentials id
    hash_table refresh_tokens id

    for sequence in users_id_seq feed_id_seq item_id_seq item_hash_id_seq; do
        state=$(psql_value "SELECT last_value || ':' || is_called FROM public.$sequence;")
        printf 'sequence\t%s\t%s\n' "$sequence" "$state"
    done
}

if [ "$output" = /dev/stdout ]; then
    write_manifest
else
    write_manifest > "$output"
    chmod 0400 "$output"
    echo "Created $output"
fi
