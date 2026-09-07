"""Temporary SQLite-to-PostgreSQL cutover importer."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys

from normalization import (
    NormalizationError,
    feed_plan,
    normalize_password,
    password_category,
    remap_item,
)

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
EXCLUDED = {"log": ("id", "ts", "level", "message"), "item_hash_new": ("id", "feed_id")}
EXCLUDED_DEFINITIONS = {
    "log": (
        (("id", "INTEGER", 0, None, 1),
         ("ts", "DATETIME", 0, "CURRENT_TIMESTAMP", 0),
         ("level", "TEXT", 0, None, 0),
         ("message", "TEXT", 1, None, 0)),
        (),
    ),
    "item_hash_new": (
        (("id", "INTEGER", 0, None, 1),
         ("feed_id", "INTEGER", 0, None, 0)),
        (("feed", "feed_id", "id", "NO ACTION", "NO ACTION", "NONE"),),
    ),
}
CORE_TABLES = ("users", "feed", "item")
LOCK_TABLES = tuple(TABLES)
BATCH_SIZE = 500
INTEGER_MIN = -(2 ** 31)
INTEGER_MAX = 2 ** 31 - 1
IDENTITY_TABLES = ("users", "feed", "item", "item_hash")
INTEGER_COLUMNS = {
    "users": ("id",), "feed": ("id", "user_id"),
    "item": ("id", "feed_id"), "feed_parser": ("feed_id",),
    "item_hash": ("id", "feed_id"), "webauthn_credentials": ("user_id",),
    "refresh_tokens": ("user_id",), "deleted_items": ("user_id", "item_id"),
}


def validate_integer_ranges(connection, present):
    # Check even discarded rows: normalization must not hide unsafe input.
    for table, columns in INTEGER_COLUMNS.items():
        if table not in present:
            continue
        for column in columns:
            nullable = (table == "item_hash" and column == "feed_id") or table == "deleted_items"
            null_check = "" if nullable else f'"{column}" IS NULL OR '
            invalid = connection.execute(
                f'SELECT 1 FROM "{table}" WHERE {null_check}'
                f'''("{column}" IS NOT NULL AND (typeof("{column}") != 'integer' '''
                f'OR "{column}" < ? OR "{column}" > ?)) LIMIT 1',
                (INTEGER_MIN, INTEGER_MAX),
            ).fetchone()
            if invalid:
                raise InspectionError("SQLite integer ID or reference is invalid or out of range.")
            if table in IDENTITY_TABLES and column == "id" and connection.execute(
                f'SELECT 1 FROM "{table}" WHERE id = ? LIMIT 1', (INTEGER_MAX,)
            ).fetchone():
                raise InspectionError("SQLite identity ID leaves no room for a generated INTEGER ID.")



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


def _source_schema(connection):
    present = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    )}
    allowed = TABLES.keys() | LEGACY.keys() | EXCLUDED.keys()
    if present - allowed:
        raise InspectionError("SQLite contains an unrecognized table without an import policy.")

    summary = {}
    for table, columns in (TABLES | LEGACY | EXCLUDED).items():
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

    for table in CORE_TABLES:
        if not summary[table]["present"] or summary[table]["missing_columns"]:
            raise InspectionError("Required SQLite core schema is missing or incomplete.")
    for table in TABLES:
        if summary[table]["present"] and summary[table]["missing_columns"]:
            raise InspectionError("A present SQLite domain table is incomplete.")
    if summary["deleted_items"]["present"] and summary["deleted_items"]["missing_columns"]:
        raise InspectionError("SQLite tombstone schema is incomplete.")
    for table in EXCLUDED:
        if summary[table]["present"] and (
            summary[table]["missing_columns"] or summary[table]["other_column_count"]
        ):
            raise InspectionError("An excluded SQLite table does not match its approved legacy schema.")
        if summary[table]["present"]:
            expected_columns, expected_foreign_keys = EXCLUDED_DEFINITIONS[table]
            columns = tuple(
                (row[1], row[2].upper(), row[3], row[4], row[5])
                for row in connection.execute(f'PRAGMA table_info("{table}")')
            )
            foreign_keys = tuple(sorted(
                (row[2], row[3], row[4], row[5], row[6], row[7])
                for row in connection.execute(f'PRAGMA foreign_key_list("{table}")')
            ))
            if columns != expected_columns or foreign_keys != expected_foreign_keys:
                raise InspectionError("An excluded SQLite table does not match its approved legacy schema.")
    return present, summary


def normalize_timestamp(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise NormalizationError("A timestamp cannot be converted safely.") from error
    else:
        raise NormalizationError("A timestamp cannot be converted safely.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _tombstone_report(connection, present):
    report = {"valid": 0, "missing": 0, "ownership_mismatched": 0}
    if "deleted_items" not in present:
        return report, 0
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
    report.update(dict(rows))
    deleted = connection.execute("""
        SELECT count(DISTINCT i.id) FROM item i JOIN feed f ON f.id = i.feed_id
        WHERE EXISTS (SELECT 1 FROM deleted_items d JOIN users u ON u.id = d.user_id
                      WHERE d.item_id = i.id AND d.user_id = f.user_id)
    """).fetchone()[0]
    return report, deleted


def _feed_parser_plan(connection, present, mapping):
    source_count = 0
    orphan_count = 0
    kept = {}
    if "feed_parser" in present:
        for feed_id, valid_for in connection.execute(
            "SELECT feed_id, valid_for FROM feed_parser ORDER BY feed_id"
        ):
            source_count += 1
            if type(feed_id) is not int:
                raise NormalizationError("Parser state contains an invalid feed reference.")
            if feed_id not in mapping:
                orphan_count += 1
                continue
            timestamp = normalize_timestamp(valid_for)
            preserved_id = mapping[feed_id]
            if preserved_id not in kept or timestamp < kept[preserved_id][1]:
                kept[preserved_id] = (preserved_id, timestamp)
    rows = [kept[key] for key in sorted(kept)]
    return {
        "source_count": source_count,
        "orphan_count": orphan_count,
        "merged_count": source_count - orphan_count - len(rows),
        "expected_target_count": len(rows),
    }, rows


def _item_hash_plan(connection, present, mapping):
    source_count = 0
    orphan_count = 0
    kept = {}
    seen_ids = set()
    if "item_hash" in present:
        for item_hash_id, value, feed_id in connection.execute(
            "SELECT id, hash, feed_id FROM item_hash ORDER BY id"
        ):
            source_count += 1
            if type(item_hash_id) is not int or item_hash_id in seen_ids or not isinstance(value, str):
                raise NormalizationError("Item hash normalization requires unique integer IDs and complete rows.")
            seen_ids.add(item_hash_id)
            if feed_id is None:
                key = (None, item_hash_id)
                remapped_feed_id = None
            elif type(feed_id) is not int:
                raise NormalizationError("Parser state contains an invalid feed reference.")
            elif feed_id not in mapping:
                orphan_count += 1
                continue
            else:
                remapped_feed_id = mapping[feed_id]
                key = (remapped_feed_id, value)
            # Rows arrive by ID, so the first row is the approved survivor.
            kept.setdefault(key, (item_hash_id, value, remapped_feed_id))
    rows = sorted(kept.values(), key=lambda row: row[0])
    return {
        "source_count": source_count,
        "orphan_count": orphan_count,
        "merged_count": source_count - orphan_count - len(rows),
        "expected_target_count": len(rows),
    }, rows


def analyze_source(connection):
    present, schema = _source_schema(connection)
    validate_integer_ranges(connection, present)
    passwords = dict.fromkeys(("null", "supported_argon2id", "legacy_plaintext",
                               "malformed_or_unsupported"), 0)
    for (value,) in connection.execute("SELECT hashed_password FROM users"):
        passwords[password_category(value)] += 1
    if passwords["malformed_or_unsupported"]:
        raise InspectionError("Password validation failed; category counts: " + json.dumps(passwords))

    normalization, feeds, mapping = feed_plan(connection, present)
    feed_parser, feed_parser_rows = _feed_parser_plan(connection, present, mapping)
    item_hash, item_hash_rows = _item_hash_plan(connection, present, mapping)
    tombstones, valid_deleted = _tombstone_report(connection, present)

    reconciliation = {}
    for table in TABLES:
        source_count = schema[table].get("rows", 0)
        if table == "feed":
            removed = normalization["merged_count"]
        elif table == "item":
            removed = valid_deleted + normalization["orphan_items"]
        elif table == "feed_parser":
            removed = feed_parser["orphan_count"] + feed_parser["merged_count"]
        elif table == "item_hash":
            removed = item_hash["orphan_count"] + item_hash["merged_count"]
        else:
            removed = 0
        reconciliation[table] = {
            "source_count": source_count,
            "removed_count": removed,
            "expected_target_count": source_count - removed,
        }

    report = {
        "schema": schema,
        "other_table_count": 0,
        "excluded_tables": {
            table: {"present": table in present, "rows": schema[table].get("rows", 0)}
            for table in EXCLUDED
        },
        "tombstones": tombstones,
        "passwords": passwords,
        "feed_normalization": normalization,
        "feed_parser_normalization": feed_parser,
        "item_hash_normalization": item_hash,
        "reconciliation": reconciliation,
    }
    plan = {
        "present": present,
        "feeds": feeds,
        "mapping": mapping,
        "feed_parser": feed_parser_rows,
        "item_hash": item_hash_rows,
    }
    return report, plan


def inspect_source(connection):
    report, _ = analyze_source(connection)
    return report


def inspect_target(connection, read_only=True):
    if read_only:
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


def _batches(cursor, columns, transform=None):
    names = tuple(columns)
    while True:
        fetched = cursor.fetchmany(BATCH_SIZE)
        if not fetched:
            return
        rows = []
        for values in fetched:
            row = dict(zip(names, values))
            if transform:
                row = transform(row)
            if row is None:
                continue
            rows.append(tuple(row[column] for column in names))
        if rows:
            yield rows


def _insert_query(table, columns):
    identifiers = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    return f'INSERT INTO public."{table}" ({identifiers}) VALUES ({placeholders})'


def _execute_many(target, query, rows):
    rows = list(rows)
    if rows:
        with target.cursor() as cursor:
            cursor.executemany(query, rows)


def _copy_table(source, target, table, columns, transform=None):
    identifiers = ", ".join(f'"{column}"' for column in columns)
    cursor = source.execute(f'SELECT {identifiers} FROM "{table}" ORDER BY rowid')
    query = _insert_query(table, columns)
    for batch in _batches(cursor, columns, transform):
        _execute_many(target, query, batch)


def _transform_user(row):
    row["hashed_password"] = normalize_password(row["hashed_password"])
    return row


def _timestamp_transform(*names):
    def transform(row):
        for name in names:
            if row[name] is not None:
                row[name] = normalize_timestamp(row[name])
        return row
    return transform


def _target_tombstones(target):
    report = {"valid": 0, "missing": 0, "ownership_mismatched": 0}
    rows = target.execute("""
        SELECT CASE
            WHEN i.id IS NULL OR u.id IS NULL THEN 'missing'
            WHEN f.user_id = d.user_id THEN 'valid'
            ELSE 'ownership_mismatched' END AS category, count(*)
        FROM pg_temp.legacy_deleted_items d
        LEFT JOIN public.item i ON i.id = d.item_id
        LEFT JOIN public.feed f ON f.id = i.feed_id
        LEFT JOIN public.users u ON u.id = d.user_id
        GROUP BY category
    """)
    report.update(dict(rows))
    deleted = target.execute("""
        DELETE FROM public.item i
        WHERE EXISTS (
            SELECT 1 FROM pg_temp.legacy_deleted_items d
            JOIN public.feed f ON f.id = i.feed_id
            JOIN public.users u ON u.id = d.user_id
            WHERE d.item_id = i.id AND f.user_id = d.user_id
        )
    """).rowcount
    return report, deleted


def synchronize_sequences(target):
    from psycopg import sql
    from uuid import uuid4

    sequences = {}
    for table in IDENTITY_TABLES:
        row = target.execute(
            "SELECT n.nspname, c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.oid = pg_get_serial_sequence(%s, 'id')::regclass",
            (f"public.{table}",),
        ).fetchone()
        if row is None:
            raise InspectionError("A required PostgreSQL identity sequence is missing.")
        maximum = target.execute(f'SELECT max(id) FROM public."{table}"').fetchone()[0]
        next_id = max(1, (maximum or 0) + 1)
        if next_id > INTEGER_MAX:
            raise InspectionError("PostgreSQL identity sequence has no INTEGER IDs remaining.")
        sequences[table] = (sql.Identifier(*row), next_id)

    def restart():
        for identifier, next_id in sequences.values():
            # RESTART is transactional, unlike setval, so failed imports restore sequences.
            target.execute(sql.SQL("ALTER SEQUENCE {} RESTART WITH {}").format(
                identifier, sql.Literal(next_id)))

    restart()
    target.execute("SAVEPOINT identity_probe")
    marker = "legacy-import-probe-" + uuid4().hex
    user_id = target.execute(
        "INSERT INTO public.users (name) VALUES (%s) RETURNING id", (marker,)
    ).fetchone()[0]
    feed_id = target.execute(
        "INSERT INTO public.feed (title, url, type, user_id) VALUES (%s, %s, %s, %s) RETURNING id",
        (marker, marker, marker, user_id),
    ).fetchone()[0]
    item_id = target.execute(
        "INSERT INTO public.item (feed_id, title, text, date, link) "
        "VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s) RETURNING id",
        (feed_id, marker, marker, marker),
    ).fetchone()[0]
    hash_id = target.execute(
        "INSERT INTO public.item_hash (hash, feed_id) VALUES (%s, %s) RETURNING id",
        (marker, feed_id),
    ).fetchone()[0]
    if (user_id, feed_id, item_id, hash_id) != tuple(
        sequences[table][1] for table in IDENTITY_TABLES
    ):
        raise InspectionError("PostgreSQL generated ID verification failed.")
    target.execute("ROLLBACK TO SAVEPOINT identity_probe")
    target.execute("RELEASE SAVEPOINT identity_probe")
    # nextval is not rolled back with the probe rows. Restore the verified next IDs.
    restart()
    return {table: {"verified": True} for table in IDENTITY_TABLES}


def execute_import(source, target):
    target.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    target.execute(
        "LOCK TABLE " + ", ".join(f'public."{table}"' for table in LOCK_TABLES)
        + " IN ACCESS EXCLUSIVE MODE"
    )
    initial_target = inspect_target(target, read_only=False)
    source_report, plan = analyze_source(source)

    _copy_table(source, target, "users", TABLES["users"], _transform_user)
    _execute_many(target, _insert_query("feed", TABLES["feed"]), [
        tuple(row[column] for column in TABLES["feed"]) for row in plan["feeds"]
    ])

    def transform_item(row):
        if row["feed_id"] not in plan["mapping"]:
            return None
        row = remap_item(row, plan["mapping"])
        row["date"] = normalize_timestamp(row["date"])
        return row

    _copy_table(source, target, "item", TABLES["item"], transform_item)
    _execute_many(target, _insert_query("feed_parser", TABLES["feed_parser"]), plan["feed_parser"])
    _execute_many(target, _insert_query("item_hash", TABLES["item_hash"]), plan["item_hash"])

    if "webauthn_credentials" in plan["present"]:
        _copy_table(source, target, "webauthn_credentials", TABLES["webauthn_credentials"],
                    _timestamp_transform("created_at", "last_used_at"))
    if "refresh_tokens" in plan["present"]:
        _copy_table(source, target, "refresh_tokens", TABLES["refresh_tokens"],
                    _timestamp_transform("expires_at", "created_at"))

    target.execute("""
        CREATE TEMP TABLE legacy_deleted_items (
            user_id INTEGER,
            item_id INTEGER
        ) ON COMMIT DROP
    """)
    if "deleted_items" in plan["present"]:
        cursor = source.execute("SELECT user_id, item_id FROM deleted_items ORDER BY rowid")
        for batch in _batches(cursor, LEGACY["deleted_items"]):
            _execute_many(
                target,
                "INSERT INTO pg_temp.legacy_deleted_items (user_id, item_id) VALUES (%s, %s)", batch
            )
    tombstones, deleted_items = _target_tombstones(target)
    if tombstones != source_report["tombstones"]:
        raise InspectionError("PostgreSQL tombstone reconciliation failed.")

    actual = {}
    for table in TABLES:
        count = target.execute(f'SELECT count(*) FROM public."{table}"').fetchone()[0]
        expected = source_report["reconciliation"][table]["expected_target_count"]
        if count != expected:
            raise InspectionError("PostgreSQL row-count reconciliation failed.")
        actual[table] = count
    sequences = synchronize_sequences(target)
    return {
        "identity_sequences": sequences,
        "mode": "execute",
        "source": source_report,
        "target_before": initial_target,
        "target_after": actual,
        "deleted_distinct_items": deleted_items,
        "transaction": "committed",
    }


def main(argv=None):
    try:
        parser = SafeParser(description=__doc__)
        parser.add_argument("--sqlite-path", default=os.environ.get("LEGACY_SQLITE_PATH"))
        parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
        modes = parser.add_mutually_exclusive_group()
        modes.add_argument("--dry-run", action="store_true", help="Inspect only, also the default")
        modes.add_argument("--execute", action="store_true", help="Transfer into an empty target")
        args = parser.parse_args(argv)
        if not args.sqlite_path or not args.database_url:
            raise InspectionError("Both SQLite path and PostgreSQL URL are required.")
        import psycopg

        source = open_source(args.sqlite_path)
        try:
            with psycopg.connect(args.database_url, connect_timeout=10) as target:
                if args.execute:
                    report = execute_import(source, target)
                else:
                    target_summary = inspect_target(target)
                    source_summary = inspect_source(source)
                    target.rollback()
                    report = {"mode": "dry-run", "source": source_summary,
                              "target": target_summary}
        finally:
            source.close()
        print(json.dumps(report, indent=2))
        return 0
    except (InspectionError, NormalizationError) as error:
        print(str(error), file=sys.stderr)
    except Exception:
        # Driver exceptions may contain URLs, paths, credentials, SQL, or row values.
        print("Import failed; check configuration, connectivity, permissions, and schema.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
