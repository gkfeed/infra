"""Regression checks for metadata cleanup around pg_dump's restrict command."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


WRAPPER = Path(__file__).resolve().parents[1] / "scripts/dbmate.sh"
BODY = """SET statement_timeout = 0;
CREATE FUNCTION public.example() RETURNS text LANGUAGE sql AS $$
-- Dumped from database version this is part of the function
SELECT 'unchanged';
$$;
COMMENT ON FUNCTION public.example() IS 'keep object comments';
\\unrestrict dbmate
"""


class SchemaDumpTests(unittest.TestCase):
    def invoke(self, source, command, failure=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "db").mkdir()
            schema = root / "db/schema.sql"
            schema.write_text(source)
            schema.chmod(0o644)
            # Stub only the database CLI; exercise the actual wrapper and awk.
            (root / "dbmate").write_text(
                '#!/bin/sh\nprintf "%s\\n" "$@" > arguments\n'
                + ("exit 23\n" if failure else "exit 0\n")
            )
            (root / "dbmate").chmod(0o755)
            result = subprocess.run(
                [str(WRAPPER), *command],
                cwd=root,
                env=dict(os.environ, PATH=f"{root}:{os.environ['PATH']}"),
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 23 if failure else 0, result.stderr)
            self.assertEqual((root / "arguments").read_text().splitlines(), command)
            self.assertEqual(schema.stat().st_mode & 0o777, 0o644)
            self.assertEqual(list((root / "db").iterdir()), [schema])
            return schema.read_text()

    def test_package_versions_produce_identical_dumps(self):
        for command in (["migrate", "--strict"], ["dump"]):
            for suffix in ("", " (Debian 17.10-1.pgdg12+1)", " (Ubuntu 17.10-1.pgdg24.04+1)"):
                with self.subTest(command=command, suffix=suffix):
                    source = (
                        "\\restrict dbmate\n\n"
                        f"-- Dumped from database version 17.10{suffix}\n"
                        f"-- Dumped by pg_dump version 18.6{suffix}\n\n" + BODY
                    )
                    self.assertEqual(
                        self.invoke(source, command), "\\restrict dbmate\n\n\n" + BODY
                    )

    def test_old_dump_without_restrict(self):
        source = "-- Dumped from database version 17.5\n-- Dumped by pg_dump version 17.5\n\n" + BODY
        self.assertEqual(self.invoke(source, ["dump"]), "\n" + BODY)

    def test_repeated_normalization_is_identical(self):
        source = "\\restrict dbmate\n\n\n" + BODY
        self.assertEqual(self.invoke(source, ["migrate", "--strict"]), source)

    def test_other_commands_leave_schema_unchanged(self):
        source = "-- Dumped from database version 17.10 (Ubuntu package)\n" + BODY
        for command in (["status"], ["new", "example"]):
            with self.subTest(command=command):
                self.assertEqual(self.invoke(source, command), source)

    def test_failed_dbmate_leaves_schema_unchanged(self):
        source = "-- Dumped from database version 17.10 (Ubuntu package)\n" + BODY
        self.assertEqual(self.invoke(source, ["migrate", "--strict"], failure=True), source)


if __name__ == "__main__":
    unittest.main()
