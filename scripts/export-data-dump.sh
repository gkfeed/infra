#!/bin/sh
set -eu
umask 077

POSTGRES_CLIENT_IMAGE=postgres:17.10-bookworm

: "${DATABASE_URL:?set DATABASE_URL to the imported PostgreSQL database}"

if [ "$#" -ne 1 ]; then
    echo "usage: DATABASE_URL=... $0 /private/path/gkfeed-data.dump" >&2
    exit 2
fi

case "$1" in
    /*) output_path=$1 ;;
    *) output_path=$PWD/$1 ;;
esac

if [ -e "$output_path" ] || [ -e "$output_path.sha256" ] || [ -e "$output_path.toc" ]; then
    echo "refusing to overwrite an existing dump or sidecar: $output_path" >&2
    exit 2
fi

output_dir=$(dirname "$output_path")
output_name=$(basename "$output_path")
install -d -m 0700 "$output_dir"

docker run --rm --network=host --user "$(id -u):$(id -g)" \
    -e DATABASE_URL \
    -v "$output_dir:/output" \
    "$POSTGRES_CLIENT_IMAGE" \
    pg_dump "$DATABASE_URL" \
        --format=custom \
        --data-only \
        --schema=public \
        --exclude-table-data=public.schema_migrations \
        --no-owner \
        --no-privileges \
        --file="/output/$output_name"

"$(dirname "$0")/check-data-dump.sh" "$output_path"

docker run --rm --user "$(id -u):$(id -g)" \
    -v "$output_dir:/input:ro" \
    "$POSTGRES_CLIENT_IMAGE" \
    pg_restore --list "/input/$output_name" > "$output_path.toc"

(
    cd "$output_dir"
    sha256sum "$output_name" > "$output_name.sha256"
)
chmod 0400 "$output_path" "$output_path.sha256" "$output_path.toc"

echo "Created $output_path"
cat "$output_path.sha256"
