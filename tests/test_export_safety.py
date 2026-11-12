import io
import json
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import tosint


class ExportSafetyTests(unittest.TestCase):
    today_stem = "2026.11.12_messages_example"

    def message(self, message_id=3):
        return SimpleNamespace(id=message_id, date=datetime(2026, 11, 10), text="New message")

    def previous_export(self, directory):
        for extension in ("jsonl", "txt"):
            Path(directory, f"2026.11.11_messages_example.{extension}").write_text(f"Previous {extension}")

    def assert_previous_export(self, directory):
        for extension in ("jsonl", "txt"):
            self.assertEqual(Path(directory, f"2026.11.11_messages_example.{extension}").read_text(),
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
                       expected_bot_id=123, output_stem=self.today_stem)
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
            partial = Path(directory, f"{self.today_stem}.jsonl")
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
            self.assertEqual(Path(result["manifest_path"]).parent.resolve(), Path(directory).resolve())
            self.assertEqual(json.loads(Path(result["manifest_path"]).read_text())["message_id"], 3)
            self.assertTrue(Path(result["text_path"]).is_file())

    def test_success_writes_daily_logs_without_a_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            self.previous_export(directory)
            app = Mock()
            app.get_messages.side_effect = [[self.message()], [], []]
            result = self.download(directory, app)
            self.assertEqual(Path(result["manifest_path"]).resolve(),
                             Path(directory, f"{self.today_stem}.jsonl").resolve())
            self.assertIn("New message", Path(result["text_path"]).read_text())
            self.assertEqual(list(Path(directory).glob(".acquisition-*")), [])

    def test_same_day_logs_are_overwritten_directly(self):
        with tempfile.TemporaryDirectory() as directory:
            self.previous_export(directory)
            for extension in ("jsonl", "txt"):
                Path(directory, f"{self.today_stem}.{extension}").write_text("Earlier today")
            app = Mock()
            app.get_messages.side_effect = [[self.message()], [], []]
            result = self.download(directory, app)
            self.assert_previous_export(directory)
            self.assertEqual(json.loads(Path(result["manifest_path"]).read_text())["message_id"], 3)
            self.assertNotIn("Earlier today", Path(result["text_path"]).read_text())

    def test_failed_same_day_run_can_leave_today_empty_but_preserves_yesterday(self):
        with tempfile.TemporaryDirectory() as directory:
            self.previous_export(directory)
            for extension in ("jsonl", "txt"):
                Path(directory, f"{self.today_stem}.{extension}").write_text("Earlier today")
            app = Mock()
            app.get_messages.side_effect = RuntimeError("request failed")
            with self.assertRaisesRegex(RuntimeError, "request failed"):
                self.download(directory, app)
            self.assert_previous_export(directory)
            self.assertEqual(Path(directory, f"{self.today_stem}.jsonl").read_text(), "")
            self.assertEqual(list(Path(directory).glob(".acquisition-*")), [])

    def test_same_day_media_references_are_loaded_before_overwriting_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            media_dir = Path(directory, "media")
            media_dir.mkdir()
            existing = media_dir / "3_report.txt"
            existing.write_bytes(b"abc")
            message = self.message()
            message.media = "MessageMediaType.DOCUMENT"
            message.document = SimpleNamespace(file_name="report.txt", file_unique_id="unique",
                                               file_size=3)
            record = {"chat_id": 123, "media_type": message.media, "file_unique_id": "unique",
                      "telegram_file_size": 3, "downloaded_file_size": 3,
                      "downloaded_file": tosint.display_path(str(existing))}
            Path(directory, f"{self.today_stem}.jsonl").write_text(json.dumps(record) + "\n")
            app = Mock()
            app.get_messages.side_effect = [[message], [], []]
            result = self.download(directory, app)
            app.download_media.assert_not_called()
            self.assertEqual(result["media_reused"], 1)
            self.assertEqual(result["media_downloaded"], 0)
            self.assertEqual(Path(json.loads(Path(result["manifest_path"]).read_text())[
                "downloaded_file"]).resolve(), existing.resolve())

    def test_other_days_preserve_messages_no_longer_returned_by_telegram(self):
        with tempfile.TemporaryDirectory() as directory:
            first_app = Mock()
            first_app.get_messages.side_effect = [[self.message(3)], [self.message(2)], []]
            first = self.download(directory, first_app)
            second_app = Mock()
            second_app.get_messages.side_effect = [[self.message(3)], [], []]
            second = self.download(directory, second_app,
                                   output_stem="2026.11.13_messages_example")
            old_ids = [row["message_id"] for row in map(
                json.loads, Path(first["manifest_path"]).read_text().splitlines())]
            new_ids = [row["message_id"] for row in map(
                json.loads, Path(second["manifest_path"]).read_text().splitlines())]
            self.assertEqual(old_ids, [3, 2])
            self.assertEqual(new_ids, [3])

    def test_first_export_creates_logs_directly_before_reading_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()

            def get_messages(chat, ids, replies):
                self.assertTrue(Path(directory, f"{self.today_stem}.jsonl").is_file())
                self.assertTrue(Path(directory, f"{self.today_stem}.txt").is_file())
                self.assertEqual(list(Path(directory).glob(".acquisition-*")), [])
                return [self.message(message_id) for message_id in ids]

            app.get_messages.side_effect = get_messages
            self.assertEqual(self.download(directory, app)["messages_exported"], 3)

    def test_media_target_avoids_both_existing_files_and_partial_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            message = self.message()
            message.document = SimpleNamespace(file_name="report.txt")
            Path(directory, "3_report.txt").touch()
            Path(directory, "3_report_1.txt.temp").touch()
            self.assertEqual(Path(tosint.build_unique_media_target(message, directory)).name,
                             "3_report_2.txt")

    def test_inferred_extension_cannot_overwrite_a_previous_attachment(self):
        with tempfile.TemporaryDirectory() as directory:
            media_dir = Path(directory, "media")
            media_dir.mkdir()
            previous = media_dir / "3_report.pdf"
            previous.write_text("Previous attachment")
            message = self.message()
            message.media = "MessageMediaType.DOCUMENT"
            message.document = SimpleNamespace(file_name="report", mime_type="application/pdf")
            app = Mock()

            def download_media(message, file_name):
                Path(file_name).write_text("New attachment")
                return file_name

            app.download_media.side_effect = download_media
            manifest = io.StringIO()
            result = {"media_downloaded": 0, "media_failed": 0,
                      "messages_exported": 0, "errors": []}
            tosint.process_download_message(message, app, 123, directory, manifest, io.StringIO(), result)
            self.assertEqual(previous.read_text(), "Previous attachment")
            payload = json.loads(manifest.getvalue())
            self.assertEqual(Path(payload["downloaded_file"]).name, "3_report_1.pdf")
            self.assertEqual(Path(payload["downloaded_file"]).read_text(), "New attachment")


if __name__ == "__main__":
    unittest.main()
