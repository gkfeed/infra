import contextlib
from datetime import timezone
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

import importer
import normalization

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHRzYWx0c2FsdA$aGFzaGhhc2hoYXNoaGFzaGhhc2hoYXNoaGFzaGhhc2g"


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'snapshot?#.sqlite'
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.executescript('''
                CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, hashed_password TEXT);
                CREATE TABLE feed (id INTEGER PRIMARY KEY, title TEXT, url TEXT, type TEXT, user_id INTEGER);
                CREATE TABLE item (id INTEGER PRIMARY KEY, feed_id INTEGER, title TEXT, text TEXT, date TEXT, link TEXT);
                CREATE TABLE deleted_items (user_id INTEGER, item_id INTEGER);
                INSERT INTO users VALUES (1, 'PRIVATE_NAME', 'PRIVATE_PASSWORD'),
                    (2, 'PRIVATE_NAME_2', '$argon2id$PRIVATE_HASH'), (3, 'PRIVATE_NAME_3', NULL);
                INSERT INTO feed VALUES (1, 'PRIVATE_TITLE', 'PRIVATE_URL', 'rss', 1);
                INSERT INTO item VALUES (1, 1, 'PRIVATE_TITLE', 'PRIVATE_BODY', '', ''),
                    (2, 1, '', '', '', '');
                INSERT INTO deleted_items VALUES (1, 1), (1, 1), (2, 1), (1, 999), (999, 1), (1, 2);
            ''')
            db.execute('UPDATE users SET hashed_password = ? WHERE id = 2', (VALID_HASH,))

    def test_integer_range_checks_cover_every_integer_column(self):
        for table, columns in importer.INTEGER_COLUMNS.items():
            for column in columns:
                with self.subTest(table=table, column=column):
                    with contextlib.closing(sqlite3.connect(':memory:')) as db:
                        db.execute(f'CREATE TABLE "{table}" (' + ', '.join(
                            f'"{name}"' for name in columns) + ')')
                        for value in (importer.INTEGER_MIN - 1, importer.INTEGER_MAX + 1,
                                      'PRIVATE_ID', 1.5):
                            db.execute(f'DELETE FROM "{table}"')
                            values = [value if name == column else 1 for name in columns]
                            db.execute(f'INSERT INTO "{table}" VALUES (' +
                                       ', '.join('?' for _ in columns) + ')', values)
                            with self.assertRaisesRegex(importer.InspectionError, 'out of range'):
                                importer.validate_integer_ranges(db, {table})
                        db.execute(f'DELETE FROM "{table}"')
                        db.execute(f'INSERT INTO "{table}" VALUES (' +
                                   ', '.join('?' for _ in columns) + ')',
                                   [importer.INTEGER_MIN for _ in columns])
                        importer.validate_integer_ranges(db, {table})
                        db.execute(f'DELETE FROM "{table}"')
                        values = [importer.INTEGER_MAX if name == column else 1 for name in columns]
                        db.execute(f'INSERT INTO "{table}" VALUES (' +
                                   ', '.join('?' for _ in columns) + ')', values)
                        if table in importer.IDENTITY_TABLES and column == 'id':
                            with self.assertRaisesRegex(importer.InspectionError, 'no room'):
                                importer.validate_integer_ranges(db, {table})
                        else:
                            importer.validate_integer_ranges(db, {table})

    @unittest.skipUnless(os.environ.get('IMPORT_TEST_DATABASE_URL'), 'requires disposable PostgreSQL')
    def test_overflow_precedes_writes_and_preserves_sequences(self):
        import psycopg
        from unittest.mock import patch
        url = os.environ['IMPORT_TEST_DATABASE_URL']
        with contextlib.closing(sqlite3.connect(self.path)) as source, source:
            source.execute('UPDATE deleted_items SET item_id = ?', (importer.INTEGER_MAX + 1,))
        with psycopg.connect(url) as db:
            before = [db.execute(f'SELECT last_value, is_called FROM public.{t}_id_seq').fetchone()
                      for t in importer.IDENTITY_TABLES]
            db.rollback()
            with contextlib.closing(importer.open_source(self.path)) as source:
                with patch.object(importer, '_copy_table') as copy:
                    with self.assertRaisesRegex(importer.InspectionError, 'out of range'):
                        importer.execute_import(source, db)
                    copy.assert_not_called()
            db.rollback()
            self.assertEqual(before, [db.execute(
                f'SELECT last_value, is_called FROM public.{t}_id_seq').fetchone()
                for t in importer.IDENTITY_TABLES])
            self.assertTrue(all(db.execute(f'SELECT count(*) FROM public."{t}"').fetchone()[0] == 0
                                for t in importer.TABLES))

    @unittest.skipUnless(os.environ.get('IMPORT_TEST_DATABASE_URL'), 'requires disposable PostgreSQL')
    def test_sequence_probes_empty_sparse_negative_and_boundary_ids(self):
        import psycopg
        url = os.environ['IMPORT_TEST_DATABASE_URL']
        for maximum in (None, -3, 0, 1500, importer.INTEGER_MAX - 1):
            with self.subTest(maximum=maximum), psycopg.connect(url) as db:
                before = [db.execute(f'SELECT last_value, is_called FROM public.{t}_id_seq').fetchone()
                          for t in importer.IDENTITY_TABLES]
                if maximum is not None:
                    db.execute('INSERT INTO public.users (id, name) VALUES (%s, %s)',
                               (maximum, 'PRIVATE_NAME'))
                    db.execute("INSERT INTO public.feed (id, title, url, type, user_id) "
                               "VALUES (%s, '', '', '', %s)", (maximum, maximum))
                    db.execute("INSERT INTO public.item (id, feed_id, title, text, date, link) "
                               "VALUES (%s, %s, '', '', CURRENT_TIMESTAMP, '')", (maximum, maximum))
                    db.execute("INSERT INTO public.item_hash (id, hash) VALUES (%s, '')", (maximum,))
                importer.synchronize_sequences(db)
                expected = max(1, (maximum or 0) + 1)
                for table in importer.IDENTITY_TABLES:
                    self.assertEqual(db.execute(f'SELECT count(*) FROM public."{table}"').fetchone()[0],
                                     int(maximum is not None))
                    self.assertEqual(db.execute(
                        f'SELECT last_value, is_called FROM public.{table}_id_seq').fetchone(),
                        (expected, False))
                    self.assertEqual(db.execute(
                        f"SELECT nextval('public.{table}_id_seq')").fetchone()[0], expected)
                db.rollback()
                self.assertEqual(before, [db.execute(
                    f'SELECT last_value, is_called FROM public.{t}_id_seq').fetchone()
                    for t in importer.IDENTITY_TABLES])

    def test_counts_and_no_record_output(self):
        db = importer.open_source(self.path)
        self.addCleanup(db.close)
        report = importer.inspect_source(db)
        self.assertEqual(report['tombstones'], {'valid': 3, 'missing': 2, 'ownership_mismatched': 1})
        self.assertEqual(report['passwords'], {'null': 1, 'legacy_plaintext': 1,
                                             'supported_argon2id': 1, 'malformed_or_unsupported': 0})
        self.assertEqual(report['other_table_count'], 0)
        self.assertNotIn('PRIVATE', json.dumps(report))
        self.assertFalse(report['schema']['refresh_tokens']['present'])

    def test_sqlite_is_read_only_and_missing_path_is_not_created(self):
        db = importer.open_source(self.path)
        self.addCleanup(db.close)
        with self.assertRaises(sqlite3.OperationalError):
            db.execute('DELETE FROM users')
        missing = self.path.parent / 'missing.sqlite'
        with self.assertRaises(sqlite3.OperationalError):
            importer.open_source(missing)
        self.assertFalse(missing.exists())

    def test_bad_arguments_and_connection_errors_are_redacted(self):
        for args in (['--PRIVATE_SECRET'], ['--dry-run', '--execute'],
                     ['--database-url', 'PRIVATE_SECRET'],
                     ['--sqlite-path', str(self.path), '--database-url', 'PRIVATE_SECRET']):
            output, error = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                self.assertEqual(importer.main(args), 1)
            self.assertEqual(output.getvalue(), '')
            self.assertNotIn('PRIVATE', error.getvalue())
            self.assertNotIn(str(self.path), error.getvalue())

    def test_missing_core_schema_fails(self):
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute('DROP TABLE users')
        db = importer.open_source(self.path)
        self.addCleanup(db.close)
        with self.assertRaises(importer.InspectionError):
            importer.inspect_source(db)

    def test_duplicate_rows_preserved_and_items_remapped(self):
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.executescript("""
                INSERT INTO feed VALUES (9, 'DIFFERENT_PRIVATE_TITLE', 'PRIVATE_URL', 'rss', 1),
                    (4, 'PRIVATE_TITLE', 'PRIVATE_URL', 'rss', 1),
                    (10, 'PRIVATE_TITLE', 'PRIVATE_URL', 'rss', 2),
                    (11, 'PRIVATE_TITLE', 'PRIVATE_URL', 'other', 1);
                UPDATE item SET feed_id = 9 WHERE id = 1;
            """)
        db = importer.open_source(self.path)
        self.addCleanup(db.close)
        report = importer.inspect_source(db)
        plan, rows, mapping = normalization.feed_plan(db, {'users', 'feed', 'item', 'deleted_items'})
        self.assertEqual([row['id'] for row in rows], [1, 10, 11])
        self.assertEqual(rows[0]['title'], 'PRIVATE_TITLE')
        self.assertEqual(plan['source_count'], 5)
        self.assertEqual(plan['merged_count'], 2)
        self.assertEqual(plan['duplicate_group_count'], 1)
        self.assertEqual(plan['duplicate_source_rows'], 3)
        self.assertEqual(plan['items_to_remap'], 1)
        self.assertEqual(mapping, {1: 1, 4: 1, 9: 1, 10: 10, 11: 11})
        item = {'id': 1, 'feed_id': 9, 'title': 'PRIVATE_TITLE'}
        self.assertEqual(normalization.remap_item(item, mapping), dict(item, feed_id=1))
        self.assertEqual(item['feed_id'], 9)
        self.assertEqual(report['reconciliation']['feed']['expected_target_count'], 3)
        self.assertEqual(report['reconciliation']['item']['expected_target_count'], 0)
        self.assertEqual(report['reconciliation']['users']['expected_target_count'], 3)
        self.assertNotIn('PRIVATE', json.dumps(report))

    def test_unsafe_dependencies_and_dangling_items(self):
        statements = [
            'CREATE TABLE PRIVATE_TABLE (feed_id INTEGER)',
            'CREATE TABLE PRIVATE_TABLE (subscription INTEGER REFERENCES feed(id))',
            'CREATE TABLE PRIVATE_TABLE (unknown_reference INTEGER)',
        ]
        for statement in statements:
            with self.subTest(statement=statement), contextlib.closing(sqlite3.connect(self.path)) as db, db:
                db.execute('BEGIN')
                db.execute(statement)
                with self.assertRaises((importer.InspectionError, normalization.NormalizationError)) as error:
                    importer.inspect_source(db)
                self.assertNotIn('PRIVATE', str(error.exception))
                db.rollback()

    def test_orphan_items_are_removed_and_reconciled(self):
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute("""
                INSERT INTO item VALUES
                    (3, 999, 'PRIVATE_ORPHAN', 'PRIVATE_BODY', '2024-01-01', 'PRIVATE_LINK')
            """)
        source = importer.open_source(self.path)
        self.addCleanup(source.close)
        report = importer.inspect_source(source)
        self.assertEqual(report['feed_normalization']['orphan_items'], 1)
        self.assertEqual(report['reconciliation']['item'], {
            'source_count': 3, 'removed_count': 3, 'expected_target_count': 0,
        })
        self.assertNotIn('PRIVATE', json.dumps(report))

    def test_parser_state_normalization_and_approved_exclusions(self):
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.executescript('''
                INSERT INTO feed VALUES (4, 'PRIVATE_OTHER_TITLE', 'PRIVATE_URL', 'rss', 1);
                CREATE TABLE feed_parser (feed_id INTEGER PRIMARY KEY, valid_for TEXT NOT NULL);
                INSERT INTO feed_parser VALUES
                    (1, '2024-02-01 00:00:00'), (4, '2024-01-01T02:00:00+02:00'),
                    (999, '2023-01-01 00:00:00');
                CREATE TABLE item_hash (id INTEGER PRIMARY KEY, hash TEXT NOT NULL, feed_id INTEGER);
                INSERT INTO item_hash VALUES
                    (1, 'PRIVATE_HASH_A', 1), (2, 'PRIVATE_HASH_A', 4),
                    (3, 'PRIVATE_HASH_B', 999), (4, 'PRIVATE_HASH_C', NULL);
                CREATE TABLE log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts DATETIME DEFAULT CURRENT_TIMESTAMP,
                    level TEXT CHECK (level IN ('DEBUG','INFO','WARN','ERROR','FATAL')),
                    message TEXT NOT NULL
                );
                INSERT INTO log VALUES (1, 'PRIVATE_TS', 'INFO', 'PRIVATE_MESSAGE');
                CREATE TABLE item_hash_new (
                    id INTEGER PRIMARY KEY, feed_id INTEGER,
                    FOREIGN KEY (feed_id) REFERENCES feed (id)
                );
                INSERT INTO item_hash_new VALUES (1, 1);
            ''')
        db = importer.open_source(self.path)
        self.addCleanup(db.close)
        report, plan = importer.analyze_source(db)
        self.assertEqual(report['feed_parser_normalization'], {
            'source_count': 3, 'orphan_count': 1, 'merged_count': 1,
            'expected_target_count': 1,
        })
        self.assertEqual(plan['feed_parser'][0][0], 1)
        self.assertEqual(plan['feed_parser'][0][1].isoformat(), '2024-01-01T00:00:00+00:00')
        self.assertEqual(report['item_hash_normalization'], {
            'source_count': 4, 'orphan_count': 1, 'merged_count': 1,
            'expected_target_count': 2,
        })
        self.assertEqual([row[0] for row in plan['item_hash']], [1, 4])
        self.assertEqual(report['excluded_tables']['log']['rows'], 1)
        self.assertEqual(report['excluded_tables']['item_hash_new']['rows'], 1)
        self.assertNotIn('PRIVATE', json.dumps(report))

    def test_excluded_table_schema_is_strict(self):
        for statement in (
            'CREATE TABLE log (id INTEGER, ts TEXT, level TEXT, message TEXT, extra TEXT)',
            'CREATE TABLE item_hash_new (id INTEGER)',
        ):
            with self.subTest(statement=statement), contextlib.closing(sqlite3.connect(self.path)) as db, db:
                db.execute('BEGIN')
                db.execute(statement)
                with self.assertRaisesRegex(importer.InspectionError, 'approved legacy schema'):
                    importer.inspect_source(db)
                db.rollback()

    def test_timestamp_normalization(self):
        naive = importer.normalize_timestamp('2024-01-01 12:30:00')
        aware = importer.normalize_timestamp('2024-01-01T14:30:00+02:00')
        self.assertEqual(naive.tzinfo, timezone.utc)
        self.assertEqual(naive, aware)
        with self.assertRaises(normalization.NormalizationError):
            importer.normalize_timestamp('PRIVATE_INVALID_TIMESTAMP')

    def test_password_rules_and_conversion(self):
        from argon2 import PasswordHasher
        self.assertIsNone(normalization.normalize_password(None))
        self.assertEqual(normalization.normalize_password(VALID_HASH), VALID_HASH)
        for plaintext in ('PRIVATE_PASSWORD', '', 'пароль'):
            encoded = normalization.normalize_password(plaintext)
            self.assertTrue(encoded.startswith('$argon2id$v=19$m=65536,t=3,p=4$'))
            self.assertTrue(PasswordHasher().verify(encoded, plaintext))
        self.assertEqual(normalization.password_category(VALID_HASH.replace('m=65536,t=3,p=4', 'p=4,t=3,m=65536')),
                         'supported_argon2id')
        invalid = ['$argon2id$PRIVATE_HASH', '$2b$12$PRIVATE_HASH', '{SHA}PRIVATE_HASH',
                   'pbkdf2_sha256$PRIVATE_HASH', b'PRIVATE_HASH',
                   VALID_HASH.replace('v=19', 'v=16'), VALID_HASH.replace('m=65536', 'm=1'),
                   VALID_HASH.replace('p=4', 'p=256'), VALID_HASH.replace('t=3', 't=0'),
                   VALID_HASH.replace('t=3', 't=3,t=3'), VALID_HASH + '=',
                   VALID_HASH.replace('m=65536', 'm=4294967296')]
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                self.assertEqual(normalization.password_category(value), 'malformed_or_unsupported')
                with self.assertRaises(normalization.NormalizationError):
                    normalization.normalize_password(value)
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE users SET hashed_password = ? WHERE id = 1', ('$PRIVATE_HASH',))
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            with self.assertRaises(importer.InspectionError) as error:
                importer.inspect_source(db)
        self.assertIn('"malformed_or_unsupported": 1', str(error.exception))
        self.assertNotIn('PRIVATE', str(error.exception))

    def test_fresh_snapshot_rechecks_normalization_and_passwords(self):
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE users SET hashed_password = ? WHERE id = 1', (VALID_HASH,))
        source = importer.open_source(self.path)
        report = importer.inspect_source(source)
        source.close()
        self.assertEqual(report['passwords']['legacy_plaintext'], 0)
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO feed SELECT 2, title, url, type, user_id FROM feed WHERE id = 1")
        source = importer.open_source(self.path)
        self.addCleanup(source.close)
        self.assertEqual(importer.inspect_source(source)['feed_normalization']['merged_count'], 1)

    @unittest.skipUnless(os.environ.get('IMPORT_TEST_DATABASE_URL'), 'requires disposable PostgreSQL')
    def test_postgres_read_only_empty_and_populated_targets(self):
        import psycopg
        url = os.environ['IMPORT_TEST_DATABASE_URL']
        with psycopg.connect(url) as db:
            report = importer.inspect_target(db)
            self.assertEqual(set(report), set(importer.TABLES))
            with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
                db.execute("INSERT INTO public.users (name) VALUES ('test')")
            db.rollback()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(importer.main(['--sqlite-path', str(self.path), '--database-url', url]), 0)
        self.assertNotIn('PRIVATE', output.getvalue())
        with contextlib.closing(sqlite3.connect(self.path)) as source, source:
            source.execute("UPDATE users SET hashed_password = '$PRIVATE_HASH' WHERE id = 1")
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            self.assertEqual(importer.main(['--sqlite-path', str(self.path), '--database-url', url]), 1)
        self.assertEqual(output.getvalue(), '')
        self.assertNotIn('PRIVATE', error.getvalue())
        self.assertIn('malformed_or_unsupported', error.getvalue())
        with psycopg.connect(url) as db:
            self.assertTrue(all(table['rows'] == 0 for table in importer.inspect_target(db).values()))
        with psycopg.connect(url) as db:
            db.execute("INSERT INTO public.users (id, name) VALUES (1, 'test')")
            db.commit()
            try:
                with psycopg.connect(url) as inspection:
                    with self.assertRaisesRegex(importer.InspectionError, 'must be empty'):
                        importer.inspect_target(inspection)
            finally:
                db.execute('DELETE FROM public.users')
                db.commit()

    @unittest.skipUnless(os.environ.get('IMPORT_TEST_DATABASE_URL'), 'requires disposable PostgreSQL')
    def test_execute_commit_rollback_reconciliation_and_repeat_rejection(self):
        import psycopg
        from argon2 import PasswordHasher

        url = os.environ['IMPORT_TEST_DATABASE_URL']
        tables = ', '.join(f'public."{table}"' for table in importer.TABLES)

        def empty_target():
            with psycopg.connect(url) as db:
                db.execute(f'TRUNCATE TABLE {tables} CASCADE')

        empty_target()
        self.addCleanup(empty_target)
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.executescript('''
                UPDATE item SET date = '2024-01-01 12:30:00';
                INSERT INTO feed VALUES (4, 'PRIVATE_OTHER_TITLE', 'PRIVATE_URL', 'rss', 1);
                INSERT INTO item VALUES
                    (3, 4, 'PRIVATE_TITLE_3', 'PRIVATE_BODY_3', '2024-01-01T14:30:00+02:00', 'PRIVATE_LINK'),
                    (5, 998, 'PRIVATE_ORPHAN_1', 'PRIVATE_BODY_5', '2024-01-01', 'PRIVATE_LINK'),
                    (6, 999, 'PRIVATE_ORPHAN_2', 'PRIVATE_BODY_6', '2024-01-01', 'PRIVATE_LINK');
                INSERT INTO deleted_items VALUES (1, 6);
                CREATE TABLE feed_parser (feed_id INTEGER PRIMARY KEY, valid_for TEXT NOT NULL);
                INSERT INTO feed_parser VALUES
                    (1, '2024-02-01 00:00:00'), (4, '2024-01-01T02:00:00+02:00'),
                    (999, '2023-01-01 00:00:00');
                CREATE TABLE item_hash (id INTEGER PRIMARY KEY, hash TEXT NOT NULL, feed_id INTEGER);
                INSERT INTO item_hash VALUES
                    (1, 'PRIVATE_HASH_A', 1), (2, 'PRIVATE_HASH_A', 4),
                    (3, 'PRIVATE_HASH_B', 999), (4, 'PRIVATE_HASH_C', NULL);
                CREATE TABLE webauthn_credentials (
                    id BLOB, user_id INTEGER, credential TEXT, name TEXT,
                    created_at TEXT, last_used_at TEXT
                );
                CREATE TABLE refresh_tokens (
                    id TEXT, user_id INTEGER, expires_at TEXT, created_at TEXT
                );
                INSERT INTO refresh_tokens VALUES
                    ('PRIVATE_TOKEN', 1, '2025-01-01T00:00:00Z', '2024-01-01 00:00:00');
                CREATE TABLE log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts DATETIME DEFAULT CURRENT_TIMESTAMP,
                    level TEXT CHECK (level IN ('DEBUG','INFO','WARN','ERROR','FATAL')),
                    message TEXT NOT NULL
                );
                INSERT INTO log VALUES (1, 'PRIVATE_TS', 'INFO', 'PRIVATE_MESSAGE');
                CREATE TABLE item_hash_new (
                    id INTEGER PRIMARY KEY, feed_id INTEGER,
                    FOREIGN KEY (feed_id) REFERENCES feed (id)
                );
                INSERT INTO item_hash_new VALUES (1, 1);
            ''')
            db.execute(
                'INSERT INTO webauthn_credentials VALUES (?, ?, ?, ?, ?, ?)',
                (b'PRIVATE_ID', 1, 'PRIVATE_CREDENTIAL', 'PRIVATE_KEY_NAME',
                 '2024-01-01 00:00:00', None),
            )
            db.execute('UPDATE item SET title = NULL WHERE id = 3')

        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            self.assertEqual(importer.main([
                '--execute', '--sqlite-path', str(self.path), '--database-url', url,
            ]), 1)
        self.assertEqual(output.getvalue(), '')
        self.assertNotIn('PRIVATE', error.getvalue())
        with psycopg.connect(url) as db:
            self.assertTrue(all(db.execute(
                f'SELECT count(*) FROM public."{table}"'
            ).fetchone()[0] == 0 for table in importer.TABLES))

        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE item SET title = 'PRIVATE_TITLE_3' WHERE id = 3")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(importer.main([
                '--execute', '--sqlite-path', str(self.path), '--database-url', url,
            ]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report['mode'], 'execute')
        self.assertEqual(report['transaction'], 'committed')
        self.assertEqual(report['target_after'], {
            'users': 3, 'feed': 1, 'item': 1, 'feed_parser': 1,
            'item_hash': 2, 'webauthn_credentials': 1, 'refresh_tokens': 1,
        })
        self.assertEqual(report['deleted_distinct_items'], 2)
        self.assertEqual(report['identity_sequences'], {
            table: {'verified': True} for table in importer.IDENTITY_TABLES
        })
        self.assertEqual(report['source']['feed_normalization']['orphan_items'], 2)
        self.assertEqual(report['source']['tombstones']['missing'], 3)
        self.assertNotIn('PRIVATE', output.getvalue())

        with psycopg.connect(url) as db:
            for table, expected in {'users': 4, 'feed': 2, 'item': 4, 'item_hash': 5}.items():
                self.assertEqual(db.execute(
                    f'SELECT last_value, is_called FROM public.{table}_id_seq').fetchone(),
                    (expected, False))
            self.assertEqual(db.execute(
                'SELECT valid_for FROM public.feed_parser WHERE feed_id = 1'
            ).fetchone()[0].isoformat(), '2024-01-01T00:00:00+00:00')
            self.assertEqual(db.execute(
                'SELECT id FROM public.item_hash ORDER BY id'
            ).fetchall(), [(1,), (4,)])
            password = db.execute(
                'SELECT hashed_password FROM public.users WHERE id = 1'
            ).fetchone()[0]
            self.assertTrue(PasswordHasher().verify(password, 'PRIVATE_PASSWORD'))
            self.assertIsNone(db.execute(
                "SELECT to_regclass('public.legacy_deleted_items')"
            ).fetchone()[0])

        before = report['target_after']
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            self.assertEqual(importer.main([
                '--execute', '--sqlite-path', str(self.path), '--database-url', url,
            ]), 1)
        self.assertEqual(output.getvalue(), '')
        self.assertIn('must be empty', error.getvalue())
        with psycopg.connect(url) as db:
            after = {table: db.execute(
                f'SELECT count(*) FROM public."{table}"'
            ).fetchone()[0] for table in importer.TABLES}
        self.assertEqual(after, before)
