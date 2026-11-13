import io
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import tosint


class MediaFilenameTests(unittest.TestCase):
    def message(self, name, message_id=1234567):
        return SimpleNamespace(id=message_id, chat=SimpleNamespace(id=456), date=datetime(2026, 11, 13),
                               media="document", document=SimpleNamespace(file_name=name, mime_type="text/plain"))

    def assert_fits(self, path, limit=255):
        self.assertLessEqual(len(os.fsencode(Path(path).name + ".temp")), limit)

    def test_short_names_keep_existing_format(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(Path(tosint.build_unique_media_target(self.message("report.txt", 42), directory)).name,
                             "42_report.txt")

    def test_long_original_filename_downloads_and_is_preserved_in_jsonl(self):
        original = "a" * 251 + ".txt"
        message = self.message(original)
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()

            def download_media(message, file_name):
                self.assert_fits(file_name)
                temporary = Path(file_name + ".temp")
                temporary.write_bytes(b"abc")
                temporary.replace(file_name)
                return file_name

            app.download_media.side_effect = download_media
            report = {"media_downloaded": 0, "media_failed": 0, "messages_exported": 0, "errors": []}
            manifest, text = io.StringIO(), io.StringIO()
            tosint.process_download_message(message, app, 456, directory, manifest, text, report)
            payload = json.loads(manifest.getvalue())
            self.assertEqual(report["media_downloaded"], 1)
            self.assertEqual(report["media_failed"], 0)
            self.assertEqual(payload["original_file_name"], original)
            self.assertEqual(Path(payload["downloaded_file"]).read_bytes(), b"abc")
            self.assertTrue(Path(payload["downloaded_file"]).name.startswith("1234567_"))
            self.assertTrue(payload["downloaded_file"].endswith(".txt"))

    def test_unicode_names_are_truncated_without_splitting_characters(self):
        with tempfile.TemporaryDirectory() as directory:
            message = self.message("\u754c" * 128 + ".pdf")
            path = tosint.build_unique_media_target(message, directory)
            self.assert_fits(path)
            name = Path(path).name
            self.assertTrue(name.endswith(".pdf"))
            stem = name.removeprefix("1234567_").removesuffix(".pdf")
            self.assertTrue(stem)
            self.assertTrue(all(character == "\u754c" for character in stem))
            Path(path + ".temp").write_bytes(b"synthetic")

    def test_collisions_reserve_space_for_growing_suffix_and_partial_files(self):
        with tempfile.TemporaryDirectory() as directory:
            message = self.message("a" * 251 + ".txt")
            paths = []
            for index in range(12):
                path = tosint.build_unique_media_target(message, directory)
                self.assert_fits(path)
                self.assertNotIn(path, paths)
                self.assertTrue(path.endswith(".txt"))
                if index:
                    self.assertTrue(Path(path).stem.endswith(f"_{index}"))
                Path(path + (".temp" if index % 2 else "")).write_text(str(index))
                paths.append(path)
            for index, path in enumerate(paths):
                self.assertEqual(Path(path + (".temp" if index % 2 else "")).read_text(), str(index))

    def test_filesystem_limit_smaller_than_portability_cap(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(os, "pathconf", return_value=48, create=True):
            path = tosint.build_unique_media_target(self.message("a" * 255 + ".zip"), directory)
            self.assert_fits(path, 48)
            self.assertTrue(path.endswith(".zip"))

    def test_extreme_extension_is_shortened_to_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = tosint.build_unique_media_target(self.message("base." + "x" * 300), directory)
            self.assert_fits(path)
            self.assertTrue(Path(path).suffix.startswith(".x"))
            Path(path + ".temp").write_bytes(b"synthetic")

    def test_pathconf_failures_and_unlimited_values_use_portable_limit(self):
        for value in (OSError("unsupported"), ValueError("unsupported"), AttributeError("unsupported"), -1, 4096):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                options = {"side_effect": value} if isinstance(value, Exception) else {"return_value": value}
                with patch.object(os, "pathconf", create=True, **options):
                    path = tosint.build_unique_media_target(self.message("a" * 300 + ".txt"), directory)
                self.assert_fits(path)

    def test_limit_too_small_fails_instead_of_looping_or_exceeding_it(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(os, "pathconf", return_value=8, create=True):
            with self.assertRaisesRegex(ValueError, "too small"):
                tosint.build_unique_media_target(self.message("a.txt"), directory)


if __name__ == "__main__":
    unittest.main()
