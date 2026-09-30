import hashlib
import io
import json
import os
import tempfile
import time
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import tosint


class ExportMetadataTests(unittest.TestCase):
    def message(self):
        return SimpleNamespace(id=42, date=datetime(2026, 9, 30, 12, tzinfo=timezone.utc),
            edit_date=datetime(2026, 9, 30, 15, tzinfo=timezone(timedelta(hours=2))),
            reply_to_message_id=41, chat=SimpleNamespace(id=123),
            media="MessageMediaType.DOCUMENT", text="Example",
            document=SimpleNamespace(file_name="archive.zip", mime_type="application/zip",
                file_size=3, file_id="telegram-id", file_unique_id="unique-id"))

    def export(self, directory, hash_media=False, skip=False):
        app = Mock()
        def download(message, file_name):
            Path(file_name).write_bytes(b"abc")
            return file_name
        app.download_media.side_effect = download
        result = {"media_downloaded": 0, "media_failed": 0, "messages_exported": 0, "errors": []}
        manifest, text = io.StringIO(), io.StringIO()
        tosint.process_download_message(self.message(), app, 999, directory, manifest, text,
            result, skip_media=skip, hash_media=hash_media)
        return result, json.loads(manifest.getvalue()), text.getvalue()

    def test_metadata_utc_and_minimal_txt_without_hashing(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(tosint, "hash_file_sha256") as hashing:
            result, payload, text = self.export(directory)
            hashing.assert_not_called()
        self.assertEqual(payload["chat_id"], 123)
        self.assertEqual(payload["date"], "2026-09-30T12:00:00Z")
        self.assertEqual(payload["edit_date"], "2026-09-30T13:00:00Z")
        self.assertEqual(payload["reply_to_message_id"], 41)
        self.assertTrue(payload["acquired_at"].endswith("Z"))
        self.assertEqual(payload["original_file_name"], "archive.zip")
        self.assertEqual(payload["telegram_file_size"], 3)
        self.assertEqual(payload["downloaded_file_size"], 3)
        self.assertNotIn("sha256", payload)
        self.assertNotIn("Acquired", text)
        self.assertNotIn("SHA", text)
        self.assertEqual(result["errors"], [])

    @contextmanager
    def local_timezone(self, name):
        try:
            with patch.dict(os.environ, {"TZ": name}):
                time.tzset()
                yield
        finally:
            time.tzset()

    @unittest.skipUnless(hasattr(time, "tzset"), "Requires process timezone control")
    def test_naive_local_dates_use_the_offset_at_the_message_date(self):
        with self.local_timezone("Europe/Rome"):
            for value, expected in [
                (datetime(2026, 9, 30, 12, 40, 35), "2026-09-30T10:40:35Z"),
                (datetime(2026, 1, 30, 12, 40, 35), "2026-01-30T11:40:35Z"),
            ]:
                with self.subTest(date=value):
                    message = self.message()
                    message.date = value
                    message.edit_date = value
                    payload = tosint.message_to_json(message)
                    self.assertEqual(payload["date"], expected)
                    self.assertEqual(payload["edit_date"], expected)
                    offset = "+02:00" if value.month == 9 else "+01:00"
                    self.assertIn(f"Date: {value.isoformat()}{offset}", tosint.message_to_text(message))

    @unittest.skipUnless(hasattr(time, "tzset"), "Requires process timezone control")
    def test_aware_utc_dates_do_not_depend_on_local_timezone(self):
        with self.local_timezone("Europe/Rome"):
            payload = tosint.message_to_json(self.message())
            self.assertEqual(payload["date"], "2026-09-30T12:00:00Z")
            self.assertEqual(payload["edit_date"], "2026-09-30T13:00:00Z")

    def test_requested_hash_matches_file_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            _, payload, text = self.export(directory, hash_media=True)
        self.assertEqual(payload["sha256"], hashlib.sha256(b"abc").hexdigest())
        self.assertNotIn(payload["sha256"], text)

    def test_skipped_media_retains_original_metadata_without_hash(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(tosint, "hash_file_sha256") as hashing:
            _, payload, _ = self.export(directory, hash_media=True, skip=True)
            hashing.assert_not_called()
        self.assertEqual(payload["mime_type"], "application/zip")
        self.assertIsNone(payload["downloaded_file_size"])
        self.assertIsNone(payload["downloaded_file"])
        self.assertNotIn("sha256", payload)

    def test_hash_failure_does_not_mark_download_as_failed(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(tosint, "hash_file_sha256", side_effect=OSError("read failed")):
            result, payload, _ = self.export(directory, hash_media=True)
        self.assertEqual(result["media_downloaded"], 1)
        self.assertEqual(result["media_failed"], 0)
        self.assertIsNone(payload["sha256"])
        self.assertEqual(payload["hash_error"], "read failed")


if __name__ == "__main__":
    unittest.main()
