#!/bin/sh
set -eu

POSTGRES_CLIENT_IMAGE=postgres:17.10-bookworm

: "${DATABASE_URL:?set DATABASE_URL to the migrated empty target}"

if [ "$#" -ne 1 ]; then
    echo "usage: DATABASE_URL=... $0 /private/path/gkfeed-data.dump" >&2
    exit 2
fi

dump_path=$(realpath "$1")
dump_dir=$(dirname "$dump_path")
dump_name=$(basename "$dump_path")

"$(dirname "$0")/check-data-dump.sh" "$dump_path"

if [ -f "$dump_path.sha256" ]; then
    (
        cd "$dump_dir"
        sha256sum --check "$dump_name.sha256"
    )
else
    echo "missing checksum sidecar: $dump_path.sha256" >&2
    exit 2
fi

target_state=$(docker run --rm --network=host -e DATABASE_URL \
    "$POSTGRES_CLIENT_IMAGE" \
    psql "$DATABASE_URL" -X -qAt -v ON_ERROR_STOP=1 -c "
        SELECT CASE WHEN
            (SELECT count(*) FROM public.schema_migrations
             WHERE version IN ('20260904184133', '20260905082946')) = 2
            AND (SELECT count(*) FROM public.users) = 0
            AND (SELECT count(*) FROM public.feed) = 0
            AND (SELECT count(*) FROM public.item) = 0
            AND (SELECT count(*) FROM public.feed_parser) = 0
            AND (SELECT count(*) FROM public.item_hash) = 0
            AND (SELECT count(*) FROM public.webauthn_credentials) = 0
            AND (SELECT count(*) FROM public.refresh_tokens) = 0
        THEN 'ready' ELSE 'not-ready' END;")

if [ "$target_state" != ready ]; then
    echo "target must contain both migrations and seven empty domain tables" >&2
    exit 1
fi

docker run --rm --network=host -e DATABASE_URL \
    -v "$dump_dir:/input:ro" \
    "$POSTGRES_CLIENT_IMAGE" \
    pg_restore \
        --dbname="$DATABASE_URL" \
        --data-only \
        --no-owner \
        --no-privileges \
        --exit-on-error \
        --single-transaction \
        "/input/$dump_name"

echo "Restored $dump_path into the migrated empty target."
