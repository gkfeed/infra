"""Temporary, read-only SQLite cutover inspection. No transfer mode exists."""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

# Only these fixed identifiers may appear in reports or SQL.
TABLES = {
    "users": ("id", "name", "hashed_password"),
    "feed": ("id", "title", "url", "type", "user_id"),
    "item": ("id", "feed_id", "title", "text", "date", "link"),
    "feed_parser": ("feed_id", "valid_for"),
    "item_hash": ("id", "hash", "feed_id"),
    "webauthn_credentials": ("id", "user_id", "credential", "name", "created_at", "last_used_at"),
    "refresh_tokens": ("id", "user_id", "expires_at", "created_at"),
}
LEGACY = {"deleted_items": ("user_id", "item_id"), "itemhash": (), "auth_refresh_tokens": ()}


class InspectionError(Exception):
    """A failure whose fixed message is safe to display."""


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's usual error includes user-supplied arguments.
        raise InspectionError("Invalid arguments; use --help for usage.")


def open_source(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    connection.execute("BEGIN")
    return connection


def inspect_source(connection):
    present = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    )}
    summary = {}
    for table, columns in (TABLES | LEGACY).items():
        if table not in present:
            summary[table] = {"present": False}
            continue
        actual = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
        summary[table] = {
            "present": True,
            "rows": connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0],
            "known_columns": [column for column in columns if column in actual],
            "missing_columns": [column for column in columns if column not in actual],
            "other_column_count": len(actual - set(columns)),
        }
    for table in ("users", "feed", "item"):
        if not summary[table]["present"] or summary[table]["missing_columns"]:
            raise InspectionError("Required SQLite core schema is missing or incomplete.")
    tombstones = {"valid": 0, "missing": 0, "ownership_mismatched": 0}
    if summary["deleted_items"]["present"]:
        if summary["deleted_items"]["missing_columns"]:
            raise InspectionError("SQLite tombstone schema is incomplete.")
        # EXISTS counts each tombstone once, even if legacy IDs are duplicated.
        rows = connection.execute("""
            SELECT CASE
                WHEN NOT EXISTS (SELECT 1 FROM item i JOIN feed f ON f.id = i.feed_id
                                 WHERE i.id = d.item_id)
                  OR NOT EXISTS (SELECT 1 FROM users u WHERE u.id = d.user_id)
                THEN 'missing'
                WHEN EXISTS (SELECT 1 FROM item i JOIN feed f ON f.id = i.feed_id
                             WHERE i.id = d.item_id AND f.user_id = d.user_id)
                THEN 'valid' ELSE 'ownership_mismatched' END AS category, count(*)
            FROM deleted_items d GROUP BY category
        """)
        tombstones.update(dict(rows))
    passwords = {"null": 0, "plaintext_candidate": 0, "encoded_candidate": 0, "non_text": 0}
    for (value,) in connection.execute("SELECT hashed_password FROM users"):
        if value is None:
            category = "null"
        elif not isinstance(value, str):
            category = "non_text"
        elif value.startswith("$"):
            category = "encoded_candidate"
        else:
            category = "plaintext_candidate"
        passwords[category] += 1
    return {"schema": summary, "other_table_count": len(present - (TABLES.keys() | LEGACY.keys())),
            "tombstones": tombstones, "passwords": passwords}


def inspect_target(connection):
    connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    result = {}
    for table, columns in TABLES.items():
        actual = {row[0] for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s", (table,)
        )}
        if not set(columns) <= actual:
            raise InspectionError("Required PostgreSQL domain schema is missing or incomplete.")
        count = connection.execute(f'SELECT count(*) FROM public."{table}"').fetchone()[0]
        if count:
            raise InspectionError("PostgreSQL domain tables must be empty.")
        result[table] = {"rows": count, "known_columns": list(columns)}
    return result


def main(argv=None):
    try:
        parser = SafeParser(description=__doc__)
        parser.add_argument("--sqlite-path", default=os.environ.get("LEGACY_SQLITE_PATH"))
        parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
        parser.add_argument("--dry-run", action="store_true", help="Inspect only, also the default")
        args = parser.parse_args(argv)
        if not args.sqlite_path or not args.database_url:
            raise InspectionError("Both SQLite path and PostgreSQL URL are required.")
        import psycopg

        source = open_source(args.sqlite_path)
        try:
            with psycopg.connect(args.database_url, connect_timeout=10) as target:
                target_summary = inspect_target(target)
                source_summary = inspect_source(source)
                target.rollback()
        finally:
            source.close()
        print(json.dumps({"mode": "dry-run", "source": source_summary,
                          "target": target_summary}, indent=2))
        return 0
    except InspectionError as error:
        print(str(error), file=sys.stderr)
    except Exception:
        # Driver exceptions may contain URLs, paths, credentials, SQL, or row values.
        print("Inspection failed; check configuration, connectivity, permissions, and schema.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
