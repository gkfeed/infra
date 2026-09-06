import contextlib
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
        for args in (['--PRIVATE_SECRET'], ['--database-url', 'PRIVATE_SECRET'],
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
            'CREATE TABLE feed_parser (feed_id INTEGER PRIMARY KEY, valid_for TEXT)',
            'CREATE TABLE item_hash (id INTEGER, hash TEXT, feed_id INTEGER)',
            'UPDATE item SET feed_id = 999 WHERE id = 1',
        ]
        for statement in statements:
            with self.subTest(statement=statement), contextlib.closing(sqlite3.connect(self.path)) as db, db:
                db.execute('BEGIN')
                db.execute(statement)
                with self.assertRaises(normalization.NormalizationError) as error:
                    importer.inspect_source(db)
                self.assertNotIn('PRIVATE', str(error.exception))
                db.rollback()

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
