import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name("export.py")
SPEC = importlib.util.spec_from_file_location("orphan_item_export", MODULE_PATH)
export = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source.sqlite"
        with contextlib.closing(sqlite3.connect(self.source)) as db, db:
            db.executescript('''
                CREATE TABLE feed (id INTEGER PRIMARY KEY);
                CREATE TABLE item (
                    id INTEGER PRIMARY KEY, feed_id INTEGER, title TEXT,
                    text TEXT, date TEXT, link TEXT
                );
                CREATE TABLE deleted_items (user_id INTEGER, item_id INTEGER);
                INSERT INTO feed VALUES (1);
                INSERT INTO item VALUES
                    (1, 1, 'kept', 'kept', '2024-01-01', 'kept'),
                    (2, 9, 'private title', 'private text', '2024-01-02', 'private link'),
                    (3, 8, 'other title', 'other text', '2024-01-03', 'other link');
                INSERT INTO deleted_items VALUES (7, 2), (7, 2), (8, 2);
            ''')

    def test_export_contains_only_orphans_and_tombstone_context(self):
        source = export.open_source(self.source)
        self.addCleanup(source.close)
        export.validate_source(source)
        output = export.create_output_directory(self.root / "private-output")
        summary, _ = export.write_export(source, output)
        self.assertEqual(summary, {
            'orphan_item_rows': 2,
            'missing_feed_ids': 2,
            'items_with_tombstones': 1,
            'items_without_tombstones': 1,
            'tombstone_rows': 3,
        })
        records = [json.loads(line) for line in (output / 'orphan_items.jsonl').read_text().splitlines()]
        self.assertEqual([record['id'] for record in records], [2, 3])
        self.assertEqual(records[0]['tombstone_rows'], 3)
        self.assertEqual(records[0]['tombstone_user_ids'], [7, 8])
        self.assertEqual(records[1]['tombstone_rows'], 0)
        self.assertEqual(os.stat(output).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(output / 'summary.json').st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(output / 'orphan_items.jsonl').st_mode & 0o777, 0o600)

    def test_source_is_read_only(self):
        source = export.open_source(self.source)
        self.addCleanup(source.close)
        with self.assertRaises(sqlite3.OperationalError):
            source.execute('DELETE FROM item')


if __name__ == "__main__":
    unittest.main()
