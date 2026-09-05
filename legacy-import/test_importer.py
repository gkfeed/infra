import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

import importer


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'snapshot?#.sqlite'
        with sqlite3.connect(self.path) as db:
            db.executescript('''
                CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, hashed_password TEXT);
                CREATE TABLE feed (id INTEGER PRIMARY KEY, title TEXT, url TEXT, type TEXT, user_id INTEGER);
                CREATE TABLE item (id INTEGER PRIMARY KEY, feed_id INTEGER, title TEXT, text TEXT, date TEXT, link TEXT);
                CREATE TABLE deleted_items (user_id INTEGER, item_id INTEGER);
                INSERT INTO users VALUES (1, 'PRIVATE_NAME', 'PRIVATE_PASSWORD'),
                    (2, 'PRIVATE_NAME_2', '$argon2id$PRIVATE_HASH'), (3, 'PRIVATE_NAME_3', NULL);
                INSERT INTO feed VALUES (1, 'PRIVATE_TITLE', 'PRIVATE_URL', 'rss', 1);
                INSERT INTO item VALUES (1, 1, 'PRIVATE_TITLE', 'PRIVATE_BODY', '', ''),
                    (2, 999, '', '', '', '');
                INSERT INTO deleted_items VALUES (1, 1), (1, 1), (2, 1), (1, 999), (999, 1), (1, 2);
                CREATE TABLE PRIVATE_TABLE (PRIVATE_COLUMN TEXT);
            ''')

    def test_counts_and_no_record_output(self):
        db = importer.open_source(self.path)
        self.addCleanup(db.close)
        report = importer.inspect_source(db)
        self.assertEqual(report['tombstones'], {'valid': 2, 'missing': 3, 'ownership_mismatched': 1})
        self.assertEqual(report['passwords'], {'null': 1, 'plaintext_candidate': 1,
                                             'encoded_candidate': 1, 'non_text': 0})
        self.assertEqual(report['other_table_count'], 1)
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
        with sqlite3.connect(self.path) as db:
            db.execute('DROP TABLE users')
        db = importer.open_source(self.path)
        self.addCleanup(db.close)
        with self.assertRaises(importer.InspectionError):
            importer.inspect_source(db)

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
