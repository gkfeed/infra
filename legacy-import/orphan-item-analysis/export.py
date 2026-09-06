"""Export orphan legacy items into a private local analysis directory."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys


class ExportError(Exception):
    """A failure with a fixed message that does not expose record data."""


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ExportError("Invalid arguments; use --help for usage.")


def open_source(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    connection.execute("BEGIN")
    return connection


def create_output_directory(base):
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(base, 0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for suffix in range(1000):
        candidate = base / f"{stamp}-{os.getpid()}-{suffix:03d}"
        try:
            candidate.mkdir(mode=0o700)
            return candidate
        except FileExistsError:
            continue
    raise ExportError("Could not create a private output directory.")


def validate_source(connection):
    required = {
        "feed": {"id"},
        "item": {"id", "feed_id", "title", "text", "date", "link"},
        "deleted_items": {"user_id", "item_id"},
    }
    present = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    )}
    for table, columns in required.items():
        if table not in present:
            raise ExportError("Required SQLite analysis schema is missing or incomplete.")
        actual = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
        if not columns <= actual:
            raise ExportError("Required SQLite analysis schema is missing or incomplete.")


def write_export(connection, output_directory):
    summary_path = output_directory / "summary.json"
    items_path = output_directory / "orphan_items.jsonl"
    counts = {
        "orphan_item_rows": 0,
        "missing_feed_ids": 0,
        "items_with_tombstones": 0,
        "items_without_tombstones": 0,
        "tombstone_rows": 0,
    }
    missing_feed_ids = set()

    query = """
        SELECT i.id, i.feed_id, i.title, i.text, i.date, i.link, d.user_id
        FROM item i
        LEFT JOIN feed f ON f.id = i.feed_id
        LEFT JOIN deleted_items d ON d.item_id = i.id
        WHERE f.id IS NULL
        ORDER BY i.id, d.rowid
    """

    current = None
    tombstone_users = []

    def emit(handle):
        if current is None:
            return
        distinct_users = list(dict.fromkeys(tombstone_users))
        record = dict(current)
        record["tombstone_rows"] = len(tombstone_users)
        record["tombstone_user_ids"] = distinct_users
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        counts["orphan_item_rows"] += 1
        counts["tombstone_rows"] += len(tombstone_users)
        if tombstone_users:
            counts["items_with_tombstones"] += 1
        else:
            counts["items_without_tombstones"] += 1

    with items_path.open("x", encoding="utf-8") as items_file:
        os.chmod(items_path, 0o600)
        for item_id, feed_id, title, text, date, link, tombstone_user_id in connection.execute(query):
            if current is None or item_id != current["id"]:
                emit(items_file)
                current = {
                    "id": item_id,
                    "missing_feed_id": feed_id,
                    "title": title,
                    "text": text,
                    "date": date,
                    "link": link,
                }
                tombstone_users = []
                missing_feed_ids.add(feed_id)
            if tombstone_user_id is not None:
                tombstone_users.append(tombstone_user_id)
        emit(items_file)

    counts["missing_feed_ids"] = len(missing_feed_ids)
    with summary_path.open("x", encoding="utf-8") as summary_file:
        os.chmod(summary_path, 0o600)
        json.dump(counts, summary_file, indent=2, sort_keys=True)
        summary_file.write("\n")
    return counts, output_directory


def main(argv=None):
    try:
        parser = SafeParser(description=__doc__)
        parser.add_argument("--sqlite-path", default=os.environ.get("LEGACY_SQLITE_PATH"))
        default_output = Path(__file__).resolve().parent / "private-output"
        parser.add_argument("--output-root", type=Path, default=default_output)
        args = parser.parse_args(argv)
        if not args.sqlite_path:
            raise ExportError("SQLite path is required.")

        connection = open_source(args.sqlite_path)
        try:
            validate_source(connection)
            output_directory = create_output_directory(args.output_root)
            counts, output_directory = write_export(connection, output_directory)
        finally:
            connection.close()
        print(json.dumps({"output_directory": str(output_directory), "summary": counts}, indent=2))
        return 0
    except ExportError as error:
        print(str(error), file=sys.stderr)
    except Exception:
        print("Export failed; check the SQLite path, permissions, schema, and free space.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
