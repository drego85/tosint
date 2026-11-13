import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import tosint


class PartialReportTests(unittest.TestCase):
    def message(self, message_id=3):
        return SimpleNamespace(id=message_id, chat=SimpleNamespace(id=999, type="private", title=None),
                               from_user=SimpleNamespace(id=123), outgoing=True,
                               date=datetime(2026, 11, 13), text="Synthetic message")

    def run_cli(self, directory, app, json_stdout=True, stop_error=None):
        def api(token, method, params=None):
            values = {"getMe": {"id": 123, "first_name": "Synthetic", "username": "synthetic_bot"},
                      "getChat": {"id": 456, "type": "private"}, "getChatMember": {"status": "member"},
                      "getChatMemberCount": 2, "getMyCommands": []}
            return {"ok": True, "result": values.get(method, {})}

        @contextlib.contextmanager
        def client(*args, **kwargs):
            try:
                yield app
            finally:
                if stop_error:
                    raise stop_error

        app.me = SimpleNamespace(id=123, is_bot=True)
        app.get_chat.return_value = SimpleNamespace(id=456, type="private", title=None)
        destination = Path(directory, "report.json")
        arguments = ["tosint.py", "-t", "123:synthetic", "-c", "456", "--download",
                     "--api-id", "1", "--api-hash", "synthetic", "--map-recipients",
                     "--download-start-id", "3", "--download-batch-size", "1",
                     "--download-dir", str(Path(directory, "data")),
                     "--session-name", str(Path(directory, "session", "bot")),
                     "--json-file", str(destination)]
        if json_stdout:
            arguments.append("--json")
        with patch.object(sys, "argv", arguments), patch.object(tosint, "telegram_api_get", side_effect=api), \
                patch.object(tosint, "telegram_api_request", side_effect=AssertionError("Unexpected network call")), \
                patch.object(tosint, "load_env_file", return_value={}), \
                patch.object(tosint, "open_download_client", client), contextlib.redirect_stdout(io.StringIO()) as output:
            status = tosint.main()
        saved = json.loads(destination.read_text())
        if json_stdout:
            self.assertEqual(json.loads(output.getvalue()), saved)
        return status, saved, output.getvalue()

    def test_transport_failure_preserves_counts_paths_and_recipient_map(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            app.get_messages.side_effect = [[self.message()], RuntimeError("Synthetic transport failure")]
            status, report, _ = self.run_cli(directory, app)
            self.assertEqual(status, 1)
            partial = report["downloads"]
            self.assertTrue(partial["failed"])
            self.assertFalse(partial["interrupted"])
            self.assertEqual(partial["messages_exported"], 1)
            self.assertEqual(partial["recipient_map"]["recipients"][0]["chat_id"], 999)
            self.assertEqual(partial["recipient_map"]["recipients"][0]["messages_observed"], 1)
            entry = next(e for e in partial["chat_exports"] if e["chat_id"] == 999)
            self.assertEqual(entry["messages_exported"], 1)
            self.assertEqual(json.loads(Path(entry["manifest_path"]).read_text())["message_id"], 3)
            self.assertIn("Synthetic transport failure", report["errors"][0])

    def test_failure_before_first_message_retains_zero_counts_and_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            app.get_messages.side_effect = RuntimeError("Synthetic failure")
            status, report, _ = self.run_cli(directory, app)
            self.assertEqual(status, 1)
            partial = report["downloads"]
            self.assertTrue(partial["failed"])
            self.assertEqual(partial["messages_exported"], 0)
            self.assertEqual(partial["recipient_map"]["recipients"], [])
            self.assertTrue(Path(partial["manifest_path"]).is_file())

    def test_text_summary_does_not_describe_failure_as_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            app.get_messages.side_effect = RuntimeError("Synthetic failure")
            status, _, output = self.run_cli(directory, app, json_stdout=False)
            self.assertEqual(status, 1)
            self.assertIn("[DOWNLOAD] Failed; partial results preserved", output)
            self.assertNotIn("[DOWNLOAD] Completed", output)

    def test_cleanup_failure_keeps_collected_map_and_export_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            app.get_messages.side_effect = [[self.message()], [], []]
            status, report, _ = self.run_cli(directory, app, stop_error=RuntimeError("Synthetic stop failure"))
            self.assertEqual(status, 1)
            self.assertTrue(report["downloads"]["failed"])
            self.assertEqual(report["downloads"]["messages_exported"], 1)
            self.assertEqual(len(report["downloads"]["recipient_map"]["recipients"]), 1)

    def test_write_failure_keeps_per_chat_media_counts(self):
        def failing_write(message, app, chat_id, download_dir, manifest, text, result, **kwargs):
            result["media_downloaded"] += 1
            raise OSError("Synthetic write failure")

        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            app.get_messages.return_value = [self.message()]
            with patch.object(tosint, "process_download_message", side_effect=failing_write):
                status, report, _ = self.run_cli(directory, app)
            self.assertEqual(status, 1)
            partial = report["downloads"]
            self.assertEqual(partial["messages_exported"], 0)
            self.assertEqual(partial["media_downloaded"], 1)
            self.assertEqual(sum(e["media_downloaded"] for e in partial["chat_exports"]), 1)


if __name__ == "__main__":
    unittest.main()
