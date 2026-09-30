import json
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import tosint


class IDScanBatchTests(unittest.TestCase):
    def run_download(self, start=123, limit=0, batch=50, missing=(), failure=None, auth="bot", progress=0):
        app = Mock()
        app.get_chat.return_value = SimpleNamespace(title="Example", type="group")
        app.get_chat_history.return_value = iter([])

        def get_messages(chat, ids, replies):
            self.assertEqual(replies, 0)
            if failure:
                raise failure
            return [SimpleNamespace(id=i, date=None if i in missing else datetime(2026, 9, 30)) for i in reversed(ids) if i != 9]

        app.get_messages.side_effect = get_messages
        pyrogram = ModuleType("pyrogram")
        pyrogram.Client = Mock()
        errors = ModuleType("pyrogram.errors")
        errors.SessionRevoked = type("SessionRevoked", (Exception,), {})

        @contextmanager
        def client(*args, **kwargs):
            yield app

        with tempfile.TemporaryDirectory() as directory, patch.dict("sys.modules", {"pyrogram": pyrogram, "pyrogram.errors": errors}), patch.object(tosint, "open_download_client", client):
            result = tosint.download_chat_content(123, 1, "fake", "session", directory, limit,
                start_message_id=start, bot_token_for_auth="fake", download_auth_mode=auth,
                batch_size=batch, progress_every=progress)
            rows = [json.loads(line) for line in Path(result["manifest_path"]).read_text().splitlines()]
        return app, result, rows

    def test_default_batches_cover_range_and_preserve_order(self):
        app, result, rows = self.run_download()
        self.assertEqual([len(call.args[1]) for call in app.get_messages.call_args_list], [50, 50, 23])
        self.assertEqual(result["messages_scanned"], 123)
        self.assertEqual(result["messages_exported"], 122)
        self.assertEqual(result["unavailable_message_ids"], 1)
        self.assertEqual([row["message_id"] for row in rows], [i for i in range(123, 0, -1) if i != 9])
        app.get_chat_history.assert_not_called()

    def test_empty_and_omitted_ids_do_not_discard_other_messages(self):
        _, result, rows = self.run_download(start=10, missing=(8, 7))
        self.assertEqual(result["messages_scanned"], 10)
        self.assertEqual(result["messages_exported"], 7)
        self.assertEqual(result["unavailable_message_ids"], 3)
        self.assertEqual([row["message_id"] for row in rows], [10, 6, 5, 4, 3, 2, 1])

    def test_export_limit_is_respected_despite_gaps(self):
        _, result, rows = self.run_download(start=20, limit=5, missing=(20, 19))
        self.assertEqual(result["messages_exported"], 5)
        self.assertEqual(result["messages_scanned"], 7)
        self.assertEqual(result["unavailable_message_ids"], 2)
        self.assertEqual([row["message_id"] for row in rows], [18, 17, 16, 15, 14])

    def test_progress_distinguishes_requested_and_unavailable_ids(self):
        with patch.object(tosint, "text_print") as output:
            self.run_download(start=10, missing=(8, 7), progress=10)
        self.assertIn("ids_scanned=10, unavailable_ids=3", output.call_args.args[0])

    def test_request_failure_is_not_silently_skipped(self):
        with self.assertRaisesRegex(RuntimeError, "request failed"):
            self.run_download(failure=RuntimeError("request failed"))

    def test_interrupt_preserves_partial_export_and_mode(self):
        _, result, rows = self.run_download(failure=KeyboardInterrupt())
        self.assertTrue(result["interrupted"])
        self.assertEqual(result["download_mode_used"], "idscan")
        self.assertEqual(rows, [])

    def test_history_does_not_fetch_id_batches(self):
        app, result, _ = self.run_download(auth="user")
        app.get_messages.assert_not_called()
        self.assertEqual(result["download_mode_used"], "history")


if __name__ == "__main__":
    unittest.main()
