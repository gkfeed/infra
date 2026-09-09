#!/bin/sh
set -eu

POSTGRES_CLIENT_IMAGE=postgres:17.10-bookworm

if [ "$#" -ne 1 ]; then
    echo "usage: $0 /private/path/gkfeed-data.dump" >&2
    exit 2
fi

dump_path=$(realpath "$1")
if [ ! -f "$dump_path" ]; then
    echo "dump does not exist: $dump_path" >&2
    exit 2
fi

dump_dir=$(dirname "$dump_path")
dump_name=$(basename "$dump_path")
work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT HUP INT TERM

docker run --rm --user "$(id -u):$(id -g)" \
    -v "$dump_dir:/input:ro" \
    "$POSTGRES_CLIENT_IMAGE" \
    pg_restore --list "/input/$dump_name" > "$work_dir/archive.toc"

awk '
    /^;/ { next }
    $4 == "TABLE" && $5 == "DATA" && $6 == "public" {
        print "TABLE DATA " $7
        next
    }
    $4 == "SEQUENCE" && $5 == "SET" && $6 == "public" {
        print "SEQUENCE SET " $7
        next
    }
    { print > unexpected }
' unexpected="$work_dir/unexpected" "$work_dir/archive.toc" \
    | LC_ALL=C sort > "$work_dir/actual"

cat > "$work_dir/expected" <<'EOF'
SEQUENCE SET feed_id_seq
SEQUENCE SET item_hash_id_seq
SEQUENCE SET item_id_seq
SEQUENCE SET users_id_seq
TABLE DATA feed
TABLE DATA feed_parser
TABLE DATA item
TABLE DATA item_hash
TABLE DATA refresh_tokens
TABLE DATA users
TABLE DATA webauthn_credentials
EOF

if [ -s "$work_dir/unexpected" ]; then
    echo "archive contains entries outside the transfer contract:" >&2
    cat "$work_dir/unexpected" >&2
    exit 1
fi

if ! diff -u "$work_dir/expected" "$work_dir/actual"; then
    echo "archive table or sequence list does not match the transfer contract" >&2
    exit 1
fi

echo "Data dump contract passed: 7 tables and 4 sequence states."
