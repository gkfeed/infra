#!/bin/sh
set -eu

# Test double for local backup round trips. Never place it on the production PATH.
: "${FAKE_TELEGRAM_DIR:?set FAKE_TELEGRAM_DIR}"

output=
document=
caption=
text=

while [ "$#" -gt 0 ]; do
	case "$1" in
	--output)
		output=$2
		shift 2
		;;
	--form)
		case "$2" in document=@*) document=${2#document=@} ;; esac
		shift 2
		;;
	--form-string)
		case "$2" in
		caption=*) caption=${2#caption=} ;;
		text=*) text=${2#text=} ;;
		esac
		shift 2
		;;
	--config | --connect-timeout | --max-time | --retry | --retry-delay | --request)
		shift 2
		;;
	--silent | --show-error | --fail-with-body)
		shift
		;;
	*)
		echo "fake curl received an unsupported argument: $1" >&2
		exit 2
		;;
	esac
done

if [ -z "$output" ]; then
	echo "fake curl did not receive --output" >&2
	exit 2
fi

install -d -m 0700 "$FAKE_TELEGRAM_DIR"
if [ -n "$document" ]; then
	if [ -n "${FAKE_TELEGRAM_REJECT_PATTERN:-}" ]; then
		case "$(basename "$document")" in
		$FAKE_TELEGRAM_REJECT_PATTERN)
			printf '{"ok":false,"description":"test rejection"}' >"$output"
			exit 22
			;;
		esac
	fi
	cp -- "$document" "$FAKE_TELEGRAM_DIR/$(basename "$document")"
	printf 'document\t%s\t%s\n' "$(basename "$document")" "$caption" \
		>>"$FAKE_TELEGRAM_DIR/messages.tsv"
elif [ -n "$text" ]; then
	printf 'text\t%s\n' "$text" >>"$FAKE_TELEGRAM_DIR/messages.tsv"
fi

printf '{"ok":true}' >"$output"
