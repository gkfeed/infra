#!/bin/sh
set -eu

dbmate "$@"

case "${1:-}" in
	migrate|dump)
		# pg_dump puts version comments after \restrict. dbmate's leading
		# comment cleanup stops at that command, leaving host-specific metadata.
		schema=db/schema.sql
		normalized=$(mktemp "$schema.XXXXXX")
		trap 'rm -f -- "$normalized"' EXIT
		trap 'exit 1' HUP INT TERM
		cp -p -- "$schema" "$normalized"
		awk '
			BEGIN { header = 1 }
			header && /^-- Dumped (from database|by pg_dump) version / { next }
			header && !/^$/ && !/^--/ && !/^\\restrict / { header = 0 }
			{ print }
		' "$schema" > "$normalized"
		if ! cmp -s -- "$schema" "$normalized"; then
			mv -- "$normalized" "$schema"
		fi
		;;
esac
