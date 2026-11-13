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
    def test_invalid_ranges_are_rejected_before_creating_directories(self):
        for options in (
            {"history_limit": -1},
            {"history_limit": 0, "start_message_id": 0},
            {"history_limit": 0, "start_message_id": -5},
        ):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                download_dir = Path(directory, "export")
                session_name = str(Path(directory, "session", "bot"))
                with self.assertRaises(ValueError):
                    tosint.download_chat_content(
                        123, 1, "fake", session_name, str(download_dir), **options
                    )
                self.assertFalse(download_dir.exists())
                self.assertFalse(Path(session_name).parent.exists())

    def run_download(self, start=123, limit=0, batch=50, missing=(), failure=None, auth="bot", progress=0, history=None):
        app = Mock()
        app.me = SimpleNamespace(id=123, is_bot=auth == "bot")
        app.get_chat.return_value = SimpleNamespace(id=123, title="Example", type="group")
        app.get_chat_history.return_value = iter([])
        if history is not None:
            app.get_chat_history.side_effect = history

        def get_messages(chat, ids, replies):
            self.assertEqual(replies, 0)
            if failure:
                raise failure
            return [SimpleNamespace(id=i, chat=SimpleNamespace(id=123), date=None if i in missing else datetime(2026, 9, 30)) for i in reversed(ids) if i != 9]

        app.get_messages.side_effect = get_messages
        pyrogram = ModuleType("pyrogram")
        pyrogram.Client = Mock()
        errors = ModuleType("pyrogram.errors")
        errors.SessionRevoked = type("SessionRevoked", (Exception,), {})

        @contextmanager
        def client(*args, **kwargs):
            yield app

        with tempfile.TemporaryDirectory() as directory, patch.dict("sys.modules", {"pyrogram": pyrogram, "pyrogram.errors": errors}), patch.object(tosint, "open_download_client", client):
            result = tosint.download_chat_content(123, 1, "fake", str(Path(directory, "sessions", "bot")), directory, limit,
                start_message_id=start, bot_token_for_auth="fake", download_auth_mode=auth,
                batch_size=batch, progress_every=progress, expected_bot_id=123)
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

    def failing_history(self, ids):
        def history(**kwargs):
            for message_id in ids:
                yield SimpleNamespace(id=message_id, chat=SimpleNamespace(id=123), date=datetime(2026, 11, 10))
            raise RuntimeError("history unavailable")
        return history

    def test_partial_history_fallback_keeps_limit_and_order_without_duplicates(self):
        app, result, rows = self.run_download(
            start=5, limit=3, auth="user", history=self.failing_history([5, 4])
        )
        self.assertEqual([row["message_id"] for row in rows], [5, 4, 3])
        self.assertEqual(app.get_messages.call_args.args[1], [3])
        self.assertEqual(result["messages_exported"], 3)
        self.assertEqual(result["start_message_id"], 3)

    def test_unlimited_fallback_scans_all_older_ids_without_sending_probe(self):
        with patch.object(tosint, "resolve_start_message_id_with_bot") as probe:
            app, result, rows = self.run_download(
                start=None, auth="user", history=self.failing_history([5, 4])
            )
        probe.assert_not_called()
        self.assertEqual([row["message_id"] for row in rows], [5, 4, 3, 2, 1])
        self.assertEqual(app.get_messages.call_args.args[1], [3, 2, 1])
        self.assertEqual(result["messages_exported"], 5)

    def test_failure_before_first_history_message_scans_from_explicit_start(self):
        _, result, rows = self.run_download(
            start=5, auth="user", history=self.failing_history([])
        )
        self.assertEqual([row["message_id"] for row in rows], [5, 4, 3, 2, 1])
        self.assertEqual(result["download_mode_used"], "idscan")

    def test_repeated_history_ids_are_exported_only_once(self):
        _, _, rows = self.run_download(
            start=5, limit=3, auth="user", history=self.failing_history([5, 5, 4])
        )
        self.assertEqual([row["message_id"] for row in rows], [5, 4, 3])

    def test_fallback_after_message_one_does_not_repeat_history(self):
        app, _, rows = self.run_download(
            start=None, auth="user", history=self.failing_history([1])
        )
        app.get_messages.assert_not_called()
        self.assertEqual([row["message_id"] for row in rows], [1])

    def test_export_write_failure_does_not_trigger_history_fallback(self):
        with patch.object(tosint, "process_download_message", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.run_download(auth="user", history=self.failing_history([5]))


if __name__ == "__main__":
    unittest.main()
