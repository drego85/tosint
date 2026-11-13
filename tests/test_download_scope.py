import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_chat_scope
import tosint


class DownloadScopeTests(unittest.TestCase):
    def message(self, message_id, chat=456, title=None):
        return SimpleNamespace(id=message_id, chat=SimpleNamespace(id=chat, type="private", title=title),
                               date=datetime(2026, 11, 13), text=f"Content for {chat}")

    def download(self, directory, app, **options):
        return test_chat_scope.ChatScopeTests().download(
            directory, app, target=456, resolved=456, scope=None, **options
        )

    def records(self, result):
        return {entry["chat_id"]: [json.loads(line) for line in Path(entry["manifest_path"]).read_text().splitlines()]
                for entry in result["chat_exports"]}

    def test_default_bot_scope_routes_interleaved_chats_and_filters_invalid_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            messages = {6: self.message(6, 999), 5: self.message(5), 4: self.message(4, 888),
                        3: self.message(3, None), 2: self.message(2, 999), 1: self.message(1, 0)}
            app.get_messages.side_effect = lambda chat, ids, replies: [messages[i] for i in reversed(ids)]
            result, primary = self.download(directory, app)
            rows = self.records(result)
            self.assertEqual(result["download_scope"], "token")
            self.assertEqual([r["message_id"] for r in primary], [5])
            self.assertEqual([r["message_id"] for r in rows[999]], [6, 2])
            self.assertEqual([r["message_id"] for r in rows[888]], [4])
            self.assertTrue(all(r["chat_id"] == cid for cid, records in rows.items() for r in records))
            self.assertEqual(result["messages_exported"], 4)
            self.assertEqual(result["messages_filtered"], 2)
            self.assertEqual(result["errors"], [])
            self.assertFalse(Path(directory, "0").exists())
            self.assertFalse(Path(directory, "None").exists())
            for entry in result["chat_exports"]:
                if entry["chat_id"] != 456:
                    self.assertEqual(Path(entry["download_dir"]).name, str(entry["chat_id"]))
                text = Path(entry["text_path"]).read_text()
                for cid in (456, 999, 888):
                    self.assertEqual(f"Content for {cid}" in text, cid == entry["chat_id"])
                self.assertFalse(Path(entry["download_dir"], "media").exists())
            app.get_chat.assert_called_once_with(456)

    def test_global_export_limit_counts_messages_across_chats(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            app.get_messages.side_effect = lambda chat, ids, replies: [self.message(i, 999 if i % 2 == 0 else 456) for i in ids]
            result, _ = self.download(directory, app, limit=2)
            self.assertEqual(result["messages_exported"], 2)
            self.assertEqual(sum(e["messages_exported"] for e in result["chat_exports"]), 2)
            app.get_messages.assert_called_once_with(456, [6, 5], replies=0)

    def test_media_and_deduplication_are_scoped_by_chat(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            first, second = self.message(5, 999), self.message(5)
            for message in (first, second):
                message.media = "document"
                message.document = SimpleNamespace(file_name="same.bin", file_unique_id="same", file_size=3)
            app.get_chat_history.return_value = iter([first, second, first])

            def download_media(message, file_name):
                Path(file_name).write_bytes(b"abc")
                return file_name

            app.download_media.side_effect = download_media
            result, _ = self.download(directory, app, mode="history", auth="bot")
            rows = self.records(result)
            self.assertEqual(result["messages_exported"], 2)
            self.assertEqual(result["media_downloaded"], 2)
            self.assertEqual(app.download_media.call_count, 2)
            paths = [Path(rows[cid][0]["downloaded_file"]).resolve() for cid in (456, 999)]
            self.assertNotEqual(paths[0], paths[1])
            self.assertTrue(all(path.read_bytes() == b"abc" for path in paths))
            self.assertTrue(all(e["media_downloaded"] == 1 for e in result["chat_exports"]))

    def test_other_chat_titles_are_sanitized_and_older_logs_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            foreign_dir = Path(directory, "999")
            foreign_dir.mkdir()
            older = foreign_dir / "2026.01.01_messages_old.jsonl"
            older.write_text("Old evidence")
            app = Mock()
            app.get_messages.return_value = [self.message(1, 999, "../Hostile / Title")]
            result, _ = self.download(directory, app, start=1)
            entry = result["chat_exports"][1]
            self.assertEqual(Path(entry["manifest_path"]).resolve().parent, foreign_dir.resolve())
            self.assertNotIn("/", Path(entry["manifest_path"]).name)
            self.assertEqual(older.read_text(), "Old evidence")

    def test_additional_chats_honor_overwrite_policy_once_per_chat(self):
        for policy, answer, allowed in (("never", "y", False), ("always", "n", True),
                                        ("ask", "n", False), ("ask", "y", True)):
            with self.subTest(policy=policy, answer=answer), tempfile.TemporaryDirectory() as directory:
                foreign_dir = Path(directory, "999")
                foreign_dir.mkdir()
                stem = tosint.build_daily_messages_stem(None, 999)
                previous = foreign_dir / f"{stem}.jsonl"
                previous.write_text("Earlier today")
                app = Mock()
                app.get_messages.return_value = [self.message(3, 999), self.message(2), self.message(1, 999)]
                with patch("builtins.input", return_value=answer) as prompt:
                    result, _ = self.download(directory, app, start=3, overwrite=policy)
                self.assertEqual(prompt.call_count, int(policy == "ask"))
                self.assertEqual(result["messages_exported"], 3 if allowed else 1)
                self.assertEqual(result["messages_skipped_overwrite"], 0 if allowed else 2)
                self.assertEqual(result["skipped_chats"], [] if allowed else [999])
                if allowed:
                    self.assertEqual(len(previous.read_text().splitlines()), 2)
                else:
                    self.assertEqual(previous.read_text(), "Earlier today")

    def test_additional_media_reuse_is_loaded_before_truncating_its_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            foreign_dir = Path(directory, "999")
            (foreign_dir / "media").mkdir(parents=True)
            attachment = foreign_dir / "media" / "3_same.bin"
            attachment.write_bytes(b"abc")
            stem = tosint.build_daily_messages_stem(None, 999)
            record = {"chat_id": 999, "media_type": "document", "file_unique_id": "same", "telegram_file_size": 3,
                      "downloaded_file_size": 3, "downloaded_file": tosint.display_path(str(attachment))}
            (foreign_dir / f"{stem}.jsonl").write_text(json.dumps(record) + "\n")
            message = self.message(1, 999)
            message.media = "document"
            message.document = SimpleNamespace(file_name="same.bin", file_unique_id="same", file_size=3)
            app = Mock()
            app.get_messages.return_value = [message]
            result, _ = self.download(directory, app, start=1, overwrite="always")
            app.download_media.assert_not_called()
            self.assertEqual(result["media_reused"], 1)
            self.assertEqual(result["chat_exports"][1]["media_reused"], 1)

    def test_skipped_chat_does_not_consume_export_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            foreign_dir = Path(directory, "999")
            foreign_dir.mkdir()
            stem = tosint.build_daily_messages_stem(None, 999)
            previous = foreign_dir / f"{stem}.txt"
            previous.write_text("Earlier today")
            app = Mock()
            messages = {3: self.message(3, 999), 2: self.message(2), 1: self.message(1)}
            app.get_messages.side_effect = lambda chat, ids, replies: [messages[i] for i in ids]
            result, primary = self.download(directory, app, start=3, limit=1, overwrite="never")
            self.assertEqual(result["messages_skipped_overwrite"], 1)
            self.assertEqual(result["messages_exported"], 1)
            self.assertEqual([r["message_id"] for r in primary], [2])
            self.assertEqual(previous.read_text(), "Earlier today")

    def test_interruption_preserves_each_partial_chat_export(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()

            def history(**kwargs):
                yield self.message(3, 999)
                yield self.message(2)
                raise KeyboardInterrupt

            app.get_chat_history.side_effect = history
            result, _ = self.download(directory, app, mode="history", auth="bot")
            self.assertTrue(result["interrupted"])
            self.assertEqual({cid: len(rows) for cid, rows in self.records(result).items()}, {456: 1, 999: 1})

    def test_secondary_write_failure_aborts_without_history_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            app.get_chat_history.return_value = iter([self.message(1, 999)])
            with patch.object(tosint, "process_download_message", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    self.download(directory, app, mode="history", auth="bot")
            app.get_messages.assert_not_called()

    def test_scope_validation_precedes_output_creation(self):
        for options in ({"download_scope": "invalid"}, {"download_scope": "token", "download_auth_mode": "user"}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    tosint.download_chat_content(456, 1, "fake", str(Path(directory, "sessions", "bot")),
                                                 str(Path(directory, "export")), 0, **options)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_json_overwrite_prompt_uses_stderr_and_eof_refuses(self):
        with patch.object(tosint, "TEXT_OUTPUT_ENABLED", False), patch("builtins.input", side_effect=EOFError), \
                patch("sys.stdout", new_callable=io.StringIO) as stdout, patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertFalse(tosint.confirm_export_overwrite())
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("overwrite", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
