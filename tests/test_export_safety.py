import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import tosint


class ExportSafetyTests(unittest.TestCase):
    def message(self, message_id=3):
        return SimpleNamespace(id=message_id, date=datetime(2026, 11, 10), text="New message")

    def previous_export(self, directory):
        for extension in ("jsonl", "txt"):
            Path(directory, f"messages_example.{extension}").write_text(f"Previous {extension}")

    def assert_previous_export(self, directory):
        for extension in ("jsonl", "txt"):
            self.assertEqual(Path(directory, f"messages_example.{extension}").read_text(),
                             f"Previous {extension}")

    def download(self, directory, app, **kwargs):
        pyrogram = ModuleType("pyrogram")
        pyrogram.Client = Mock()
        errors = ModuleType("pyrogram.errors")
        errors.SessionRevoked = type("SessionRevoked", (Exception,), {})

        @contextmanager
        def client(*args, **options):
            yield app

        options = dict(start_message_id=3, bot_token_for_auth="fake",
                       download_auth_mode="bot", progress_every=0, batch_size=1,
                       expected_bot_id=123)
        options.update(kwargs)
        app.get_chat.return_value = SimpleNamespace(title="Example", type="group")
        app.me = SimpleNamespace(id=123, is_bot=True)
        with patch.dict("sys.modules", {"pyrogram": pyrogram, "pyrogram.errors": errors}), patch.object(
            tosint, "open_download_client", client
        ), patch.object(tosint, "text_print"):
            return tosint.download_chat_content(123, 1, "fake", "session", directory, 0, **options)

    def test_start_id_failure_does_not_truncate_previous_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            self.previous_export(directory)
            with patch.object(tosint, "resolve_start_message_id_with_bot",
                              side_effect=tosint.TelegramAPIError("sendMessage: timeout")):
                with self.assertRaises(tosint.TelegramAPIError):
                    self.download(directory, Mock(), start_message_id=None, bot_token_for_start="fake")
            self.assert_previous_export(directory)

    def test_failed_download_preserves_old_media_and_partial_new_export(self):
        with tempfile.TemporaryDirectory() as directory:
            self.previous_export(directory)
            media_dir = Path(directory, "media")
            media_dir.mkdir()
            old_media = media_dir / "3_report.txt"
            old_media.write_text("Previous attachment")
            message = self.message()
            message.media = "MessageMediaType.DOCUMENT"
            message.document = SimpleNamespace(file_name="report.txt")
            app = Mock()
            app.get_messages.side_effect = [[message], RuntimeError("request failed")]

            def download_media(message, file_name):
                Path(file_name).write_text("New attachment")
                return file_name

            app.download_media.side_effect = download_media
            with self.assertRaisesRegex(RuntimeError, "request failed"):
                self.download(directory, app)
            self.assert_previous_export(directory)
            self.assertEqual(old_media.read_text(), "Previous attachment")
            self.assertEqual((media_dir / "3_report_1.txt").read_text(), "New attachment")
            partial = next(Path(directory).glob(".acquisition-*/messages_example.jsonl"))
            payload = json.loads(partial.read_text())
            self.assertEqual(payload["message_id"], 3)
            self.assertTrue(Path(payload["downloaded_file"]).is_file())

    def test_interrupt_preserves_previous_and_returns_partial_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            self.previous_export(directory)
            app = Mock()
            app.get_messages.side_effect = [[self.message()], KeyboardInterrupt()]
            result = self.download(directory, app)
            self.assertTrue(result["interrupted"])
            self.assert_previous_export(directory)
            self.assertIn(".acquisition-", result["manifest_path"])
            self.assertEqual(json.loads(Path(result["manifest_path"]).read_text())["message_id"], 3)
            self.assertTrue(Path(result["text_path"]).is_file())

    def test_success_publishes_both_logs_and_removes_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            self.previous_export(directory)
            app = Mock()
            app.get_messages.side_effect = [[self.message()], [], []]
            result = self.download(directory, app)
            self.assertEqual(Path(result["manifest_path"]).resolve(),
                             Path(directory, "messages_example.jsonl").resolve())
            self.assertIn("New message", Path(result["text_path"]).read_text())
            self.assertEqual(list(Path(directory).glob(".acquisition-*")), [])

    def test_second_log_publish_failure_rolls_back_the_first(self):
        with tempfile.TemporaryDirectory() as directory:
            self.previous_export(directory)
            replace = os.replace

            def fail_second_log(source, target):
                if Path(source).name == "messages_example.txt" and Path(target).parent == Path(directory):
                    raise OSError("publication failed")
                return replace(source, target)

            app = Mock()
            app.get_messages.side_effect = [[self.message()], [], []]
            with patch.object(tosint.os, "replace", side_effect=fail_second_log):
                with self.assertRaisesRegex(OSError, "publication failed"):
                    self.download(directory, app)
            self.assert_previous_export(directory)
            partial = next(Path(directory).glob(".acquisition-*/messages_example.jsonl"))
            self.assertEqual(json.loads(partial.read_text())["message_id"], 3)

    def test_media_target_avoids_both_existing_files_and_partial_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            message = self.message()
            message.document = SimpleNamespace(file_name="report.txt")
            Path(directory, "3_report.txt").touch()
            Path(directory, "3_report_1.txt.temp").touch()
            self.assertEqual(Path(tosint.build_unique_media_target(message, directory)).name,
                             "3_report_2.txt")


if __name__ == "__main__":
    unittest.main()
