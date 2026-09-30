import io
import json
import tempfile
import unittest
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from tosint import process_download_message


class MediaDownloadTests(unittest.TestCase):
    def process(self, media, directory, app, skip_media=False):
        message = SimpleNamespace(id=42, date=datetime(2026, 9, 30), media=media, text="Example")
        result = {"media_downloaded": 0, "media_failed": 0, "messages_exported": 0, "errors": []}
        manifest, text = io.StringIO(), io.StringIO()
        process_download_message(message, app, 123, directory, manifest, text, result, skip_media)
        return result, json.loads(manifest.getvalue()), text.getvalue()

    def test_excluded_types_are_exported_without_downloads_or_directory(self):
        excluded = ("STICKER", "ANIMATION", "WEB_PAGE_PREVIEW", "DICE", "CONTACT", "LOCATION", "VENUE", "POLL", "GAME", "INVOICE", "UNKNOWN")
        for kind in excluded:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                app = Mock()
                result, payload, text = self.process(f"MessageMediaType.{kind}", directory, app)
                app.download_media.assert_not_called()
                self.assertFalse(Path(directory, "media").exists())
                self.assertEqual(result["media_failed"], 0)
                self.assertEqual(result["messages_exported"], 1)
                self.assertIsNone(payload["downloaded_file"])
                self.assertIn(kind, text)

    def test_allowed_types_are_downloaded_with_enum_and_string_values(self):
        types = Enum("MessageMediaType", {kind.upper(): kind for kind in ("photo", "video", "document", "audio", "voice", "video_note")})
        for kind in types:
            for representation in (kind, str(kind), kind.value):
                with self.subTest(media=representation), tempfile.TemporaryDirectory() as directory:
                    app = Mock()
                    app.download_media.side_effect = lambda message, file_name: file_name
                    result, payload, _ = self.process(representation, directory, app)
                    app.download_media.assert_called_once()
                    self.assertTrue(Path(directory, "media").is_dir())
                    self.assertEqual(result["media_downloaded"], 1)
                    self.assertEqual(result["media_failed"], 0)
                    self.assertIsNotNone(payload["downloaded_file"])

    def test_skip_media_overrides_allowed_type(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            result, _, _ = self.process("photo", directory, app, skip_media=True)
            app.download_media.assert_not_called()
            self.assertFalse(Path(directory, "media").exists())
            self.assertEqual(result["messages_exported"], 1)

    def test_actual_download_failure_is_counted_and_message_exported(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            app.download_media.side_effect = RuntimeError("Download unavailable")
            result, payload, _ = self.process("document", directory, app)
            self.assertEqual(result["media_failed"], 1)
            self.assertEqual(result["messages_exported"], 1)
            self.assertIsNone(payload["downloaded_file"])
            self.assertIn("Download unavailable", result["errors"][0])


if __name__ == "__main__":
    unittest.main()
