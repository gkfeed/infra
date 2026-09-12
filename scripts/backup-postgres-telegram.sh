#!/bin/sh
set -eu
umask 077

POSTGRES_CLIENT_IMAGE=postgres:17.10-bookworm
TELEGRAM_API_ROOT=https://api.telegram.org

if [ "$#" -ne 1 ]; then
	echo "usage: $0 /private/path/backup.env" >&2
	exit 2
fi

env_file=$1
if [ ! -f "$env_file" ]; then
	echo "backup environment file does not exist: $env_file" >&2
	exit 2
fi

env_mode=$(stat -c %a "$env_file")
case "$env_mode" in
400 | 600) ;;
*)
	echo "backup environment file must have mode 0400 or 0600: $env_file" >&2
	exit 2
	;;
esac

# The operator owns this trusted shell environment file.
# shellcheck disable=SC1090
. "$env_file"

: "${BACKUP_DATABASE_URL:?set BACKUP_DATABASE_URL in the backup environment file}"
: "${TELEGRAM_BOT_TOKEN:?set TELEGRAM_BOT_TOKEN in the backup environment file}"
: "${TELEGRAM_CHAT_ID:?set TELEGRAM_CHAT_ID in the backup environment file}"
: "${BACKUP_SPOOL_DIR:?set BACKUP_SPOOL_DIR in the backup environment file}"

BACKUP_PART_BYTES=${BACKUP_PART_BYTES:-45000000}
BACKUP_MIN_FREE_BYTES=${BACKUP_MIN_FREE_BYTES:-5368709120}

case "$BACKUP_SPOOL_DIR" in
/*) ;;
*)
	echo "BACKUP_SPOOL_DIR must be an absolute path" >&2
	exit 2
	;;
esac
if [ "$BACKUP_SPOOL_DIR" = / ]; then
	echo "BACKUP_SPOOL_DIR must not be /" >&2
	exit 2
fi

case "$BACKUP_PART_BYTES" in
*[!0-9]* | '')
	echo "BACKUP_PART_BYTES must be an integer" >&2
	exit 2
	;;
esac
case "$BACKUP_MIN_FREE_BYTES" in
*[!0-9]* | '')
	echo "BACKUP_MIN_FREE_BYTES must be an integer" >&2
	exit 2
	;;
esac
if [ "$BACKUP_PART_BYTES" -lt 1000000 ] || [ "$BACKUP_PART_BYTES" -gt 49000000 ]; then
	echo "BACKUP_PART_BYTES must be between 1000000 and 49000000" >&2
	exit 2
fi

for command_name in curl df docker install logger mktemp sha256sum split stat; do
	if ! command -v "$command_name" >/dev/null 2>&1; then
		echo "required command is missing: $command_name" >&2
		exit 2
	fi
done

pending_dir=$BACKUP_SPOOL_DIR/pending
install -d -m 0700 "$BACKUP_SPOOL_DIR" "$pending_dir"

response_file=$(mktemp "$BACKUP_SPOOL_DIR/.telegram-response.XXXXXX")
curl_config=$(mktemp "$BACKUP_SPOOL_DIR/.telegram-curl.XXXXXX")
work_dir=
current_step=initialization
env_ready=1

log_message() {
	level=$1
	shift
	message=$*
	printf '%s: %s\n' "$level" "$message" >&2
	logger -t gkfeed-postgres-backup -- "$level: $message" 2>/dev/null || true
}

write_curl_config() {
	endpoint=$1
	printf 'url = "%s/bot%s/%s"\n' \
		"$TELEGRAM_API_ROOT" "$TELEGRAM_BOT_TOKEN" "$endpoint" >"$curl_config"
}

telegram_ok() {
	grep -Eq '"ok"[[:space:]]*:[[:space:]]*true' "$response_file"
}

send_text_best_effort() {
	text=$1
	write_curl_config sendMessage
	if ! curl --config "$curl_config" --silent --show-error --fail-with-body \
		--connect-timeout 15 --max-time 60 --retry 2 --retry-delay 2 \
		--request POST \
		--form-string "chat_id=$TELEGRAM_CHAT_ID" \
		--form-string "text=$text" \
		--output "$response_file"; then
		return 1
	fi
	telegram_ok
}

cleanup() {
	rm -f -- "$response_file" "$curl_config"
	if [ -n "$work_dir" ]; then
		case "$work_dir" in
		"$BACKUP_SPOOL_DIR"/.work.*) rm -rf -- "$work_dir" ;;
		esac
	fi
}

on_exit() {
	status=$?
	if [ "$status" -ne 0 ]; then
		failure="backup failed during $current_step on $(hostname)"
		log_message ERROR "$failure"
		if [ "${env_ready:-0}" = 1 ]; then
			send_text_best_effort "gkfeed PostgreSQL $failure" || true
		fi
	fi
	cleanup
}
trap on_exit EXIT
trap 'exit 130' HUP INT TERM

export DATABASE_URL=$BACKUP_DATABASE_URL

psql_value() {
	docker run --rm --network=host -e DATABASE_URL \
		"$POSTGRES_CLIENT_IMAGE" \
		sh -ceu 'exec psql "$DATABASE_URL" -X -qAt -v ON_ERROR_STOP=1 -c "$1"' \
		sh "$1"
}

upload_document() {
	file_path=$1
	caption=$2
	write_curl_config sendDocument
	if ! curl --config "$curl_config" --silent --show-error --fail-with-body \
		--connect-timeout 15 --max-time 600 --retry 3 --retry-delay 5 \
		--request POST \
		--form-string "chat_id=$TELEGRAM_CHAT_ID" \
		--form "document=@$file_path" \
		--form-string "caption=$caption" \
		--output "$response_file"; then
		return 1
	fi
	telegram_ok
}

remove_sent_backup() {
	backup_dir=$1
	case "$backup_dir" in
	"$pending_dir"/*) rm -rf -- "$backup_dir" ;;
	*)
		log_message ERROR "refusing to remove unexpected path: $backup_dir"
		return 1
		;;
	esac
}

upload_backup() {
	backup_dir=$1
	manifest_count=0
	manifest=
	for candidate in "$backup_dir"/*.manifest; do
		[ -f "$candidate" ] || continue
		manifest=$candidate
		manifest_count=$((manifest_count + 1))
	done
	if [ "$manifest_count" -ne 1 ]; then
		log_message ERROR "pending backup has $manifest_count manifests: $backup_dir"
		return 1
	fi

	backup_id=$(basename "$manifest" .manifest)
	payload_list=$backup_dir/.payloads
	awk -F '\t' '$1 == "payload" { print $2 }' "$manifest" >"$payload_list"
	if [ ! -s "$payload_list" ]; then
		log_message ERROR "manifest has no payloads: $manifest"
		rm -f -- "$payload_list"
		return 1
	fi

	while IFS= read -r payload_name; do
		case "$payload_name" in
		'' | */* | .*)
			log_message ERROR "unsafe payload name in $manifest"
			rm -f -- "$payload_list"
			return 1
			;;
		esac
		payload_path=$backup_dir/$payload_name
		if [ ! -f "$payload_path" ]; then
			log_message ERROR "missing backup payload: $payload_path"
			rm -f -- "$payload_list"
			return 1
		fi
		sent_marker=$backup_dir/.sent-$payload_name
		if [ -f "$sent_marker" ]; then
			continue
		fi
		log_message INFO "uploading $payload_name"
		if ! upload_document "$payload_path" "$backup_id payload $payload_name"; then
			log_message ERROR "Telegram rejected $payload_name"
			rm -f -- "$payload_list"
			return 1
		fi
		: >"$sent_marker"
	done <"$payload_list"
	rm -f -- "$payload_list"

	log_message INFO "uploading commit manifest $(basename "$manifest")"
	if ! upload_document "$manifest" "$backup_id complete; download this manifest last"; then
		log_message ERROR "Telegram rejected $(basename "$manifest")"
		return 1
	fi

	remove_sent_backup "$backup_dir"
	log_message INFO "Telegram committed $backup_id"
}

current_step='retrying pending uploads'
upload_failed=0
for backup_dir in "$pending_dir"/*; do
	[ -d "$backup_dir" ] || continue
	if ! upload_backup "$backup_dir"; then
		upload_failed=1
	fi
done

current_step='checking spool free space'
available_kib=$(df -Pk "$BACKUP_SPOOL_DIR" | awk 'NR == 2 { print $4 }')
case "$available_kib" in
*[!0-9]* | '')
	log_message ERROR "could not read free space for $BACKUP_SPOOL_DIR"
	exit 1
	;;
esac
available_bytes=$((available_kib * 1024))
if [ "$available_bytes" -lt "$BACKUP_MIN_FREE_BYTES" ]; then
	log_message ERROR "less than $BACKUP_MIN_FREE_BYTES bytes free in $BACKUP_SPOOL_DIR"
	exit 1
fi

created_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_id=gkfeed-$timestamp
backup_dir=$pending_dir/$backup_id
if [ -e "$backup_dir" ]; then
	log_message ERROR "backup identifier already exists: $backup_dir"
	exit 1
fi

work_dir=$(mktemp -d "$BACKUP_SPOOL_DIR/.work.$backup_id.XXXXXX")
dump_name=$backup_id.dump
dump_path=$work_dir/$dump_name
toc_path=$work_dir/$backup_id.toc
manifest=$work_dir/$backup_id.manifest

current_step='reading database identity'
database_name=$(psql_value 'SELECT current_database();')
migration_version=$(psql_value 'SELECT max(version) FROM public.schema_migrations;')
if [ -z "$migration_version" ]; then
	log_message ERROR 'database has no recorded migrations'
	exit 1
fi

current_step='creating the custom dump'
docker run --rm --network=host --user "$(id -u):$(id -g)" \
	-e DATABASE_URL \
	-e DUMP_NAME="$dump_name" \
	-v "$work_dir:/output" \
	"$POSTGRES_CLIENT_IMAGE" \
	sh -ceu 'exec pg_dump "$DATABASE_URL" \
        --format=custom \
        --no-owner \
        --no-privileges \
        --file="/output/$DUMP_NAME"'

current_step='verifying the custom dump'
docker run --rm --user "$(id -u):$(id -g)" \
	-v "$work_dir:/input:ro" \
	"$POSTGRES_CLIENT_IMAGE" \
	pg_restore --list "/input/$dump_name" >"$toc_path"

dump_bytes=$(wc -c <"$dump_path" | tr -d ' ')
dump_sha256=$(sha256sum "$dump_path" | awk '{ print $1 }')

current_step='preparing Telegram payloads'
if [ "$dump_bytes" -gt "$BACKUP_PART_BYTES" ]; then
	split -d -a 4 -b "$BACKUP_PART_BYTES" -- \
		"$dump_path" "$work_dir/$dump_name.part-"
	rm -f -- "$dump_path"
fi

{
	printf 'format\tgkfeed-postgres-backup-v1\n'
	printf 'created_utc\t%s\n' "$created_utc"
	printf 'database\t%s\n' "$database_name"
	printf 'migration_version\t%s\n' "$migration_version"
	printf 'client_image\t%s\n' "$POSTGRES_CLIENT_IMAGE"
	printf 'dump_name\t%s\n' "$dump_name"
	printf 'dump_bytes\t%s\n' "$dump_bytes"
	printf 'dump_sha256\t%s\n' "$dump_sha256"
	for payload_path in "$work_dir/$dump_name" "$work_dir/$dump_name".part-*; do
		[ -f "$payload_path" ] || continue
		payload_name=$(basename "$payload_path")
		payload_bytes=$(wc -c <"$payload_path" | tr -d ' ')
		payload_sha256=$(sha256sum "$payload_path" | awk '{ print $1 }')
		printf 'payload\t%s\t%s\t%s\n' \
			"$payload_name" "$payload_bytes" "$payload_sha256"
	done
} >"$manifest"

if ! grep -q '^payload'"$(printf '\t')" "$manifest"; then
	log_message ERROR 'no Telegram payload was created'
	exit 1
fi

chmod 0400 "$work_dir"/*
mv -- "$work_dir" "$backup_dir"
work_dir=

current_step='uploading the new backup'
if ! upload_backup "$backup_dir"; then
	upload_failed=1
fi

if [ "$upload_failed" -ne 0 ]; then
	current_step='uploading one or more queued backups'
	exit 1
fi

current_step=complete
log_message INFO "backup completed: $backup_id ($dump_bytes bytes)"
