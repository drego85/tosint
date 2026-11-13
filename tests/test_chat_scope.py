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


class ChatScopeTests(unittest.TestCase):
    def message(self, message_id, chat_id=123, dated=True):
        return SimpleNamespace(id=message_id, chat=SimpleNamespace(id=chat_id),
                               date=datetime(2026, 11, 13) if dated else None,
                               text=f"Message {message_id}")

    def download(self, directory, app, target=123, resolved=123, mode="auto", limit=0, start=6, auth=None):
        auth = auth or ("user" if mode == "history" else "bot")
        app.me = SimpleNamespace(id=123, is_bot=auth == "bot")
        app.get_chat.return_value = SimpleNamespace(id=resolved, title="Example", type="private")
        package = ModuleType("pyrogram")
        package.Client = Mock()
        errors = ModuleType("pyrogram.errors")
        errors.SessionRevoked = type("SessionRevoked", (Exception,), {})

        @contextmanager
        def client(*args, **kwargs):
            yield app

        with patch.dict("sys.modules", {"pyrogram": package, "pyrogram.errors": errors}), patch.object(
            tosint, "open_download_client", client
        ):
            result = tosint.download_chat_content(
                target, 1, "fake", str(Path(directory, "sessions", "bot")),
                str(Path(directory, "export")), limit, start_message_id=start,
                download_auth_mode=auth,
                download_mode=mode, bot_token_for_auth="123:fake", progress_every=0
            )
        rows = [json.loads(line) for line in Path(result["manifest_path"]).read_text().splitlines()]
        return result, rows

    def test_mixed_batches_filter_other_unknown_and_empty_messages_without_using_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            messages = {6: self.message(6, 999), 5: self.message(5, None),
                        4: self.message(4, None, dated=False), 3: self.message(3),
                        2: self.message(2, 888), 1: self.message(1)}
            app = Mock()
            app.get_messages.side_effect = lambda chat, ids, replies: [messages[i] for i in reversed(ids)]
            result, rows = self.download(directory, app, limit=2)
            self.assertEqual([row["message_id"] for row in rows], [3, 1])
            self.assertTrue(all(row["chat_id"] == 123 for row in rows))
            self.assertEqual(result["messages_exported"], 2)
            self.assertEqual(result["messages_filtered"], 3)
            self.assertEqual(result["unavailable_message_ids"], 1)
            self.assertEqual(result["messages_scanned"], 6)

    def test_only_other_chat_messages_produce_an_empty_export_not_a_false_success_count(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            app.get_messages.side_effect = lambda chat, ids, replies: [self.message(i, 999) for i in ids]
            result, rows = self.download(directory, app)
            self.assertEqual(rows, [])
            self.assertEqual(result["messages_exported"], 0)
            self.assertEqual(result["messages_filtered"], 6)
            self.assertEqual(result["unavailable_message_ids"], 0)

    def test_username_target_is_resolved_before_matching_and_requesting_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            app.get_messages.return_value = [self.message(1, -1001234567890)]
            result, rows = self.download(directory, app, target="@example", resolved=-1001234567890, start=1)
            app.get_chat.assert_called_once_with("@example")
            app.get_messages.assert_called_once_with(-1001234567890, [1], replies=0)
            self.assertEqual(rows[0]["chat_id"], -1001234567890)
            self.assertEqual(result["messages_filtered"], 0)

    def test_unknown_username_target_stops_before_export_files_or_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            app.get_chat.side_effect = RuntimeError("not found")
            with patch.object(tosint, "resolve_start_message_id_with_bot") as probe:
                with self.assertRaisesRegex(RuntimeError, "resolve the target chat"):
                    self.download(directory, app, target="@example", resolved=None)
            self.assertFalse(Path(directory, "export").exists())
            probe.assert_not_called()
            app.get_messages.assert_not_called()

    def test_conflicting_resolved_numeric_target_stops_before_export(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                self.download(directory, app, target=123, resolved=999)
            self.assertFalse(Path(directory, "export").exists())
            app.get_messages.assert_not_called()

    def test_numeric_target_still_filters_when_chat_metadata_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            app.get_chat.side_effect = RuntimeError("metadata unavailable")
            app.get_messages.return_value = [self.message(1)]
            result, rows = self.download(directory, app, start=1)
            self.assertEqual(rows[0]["chat_id"], 123)
            self.assertEqual(result["messages_filtered"], 0)

    def test_history_limit_counts_only_matching_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            messages = [self.message(6, 999), self.message(5), self.message(4, None),
                        self.message(3), self.message(2)]
            app.get_chat_history.side_effect = lambda **kwargs: iter(messages[:kwargs.get("limit") or None])
            result, rows = self.download(directory, app, mode="history", limit=2)
            self.assertEqual([row["message_id"] for row in rows], [5, 3])
            self.assertEqual(result["messages_filtered"], 2)
            app.get_messages.assert_not_called()

    def test_fallback_continues_below_oldest_matching_message(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()

            def history(**kwargs):
                yield self.message(6, 999)
                yield self.message(5)
                raise RuntimeError("history failed")

            app.get_chat_history.side_effect = history
            app.get_messages.side_effect = lambda chat, ids, replies: [
                self.message(i, 999 if i == 4 else 123) for i in ids
            ]
            result, rows = self.download(directory, app, auth="user", limit=2)
            self.assertEqual([row["message_id"] for row in rows], [5, 3])
            self.assertEqual(result["messages_filtered"], 2)
            self.assertEqual(result["start_message_id"], 4)

    def test_foreign_or_unattributed_media_never_reaches_download_hash_or_export(self):
        for actual_chat in (999, None, "123", True):
            with self.subTest(chat=actual_chat), tempfile.TemporaryDirectory() as directory:
                message = self.message(42, actual_chat)
                message.media = "document"
                message.document = SimpleNamespace(file_name="foreign.bin", file_unique_id="foreign", file_size=3)
                app = Mock()
                result = {"messages_exported": 0, "media_downloaded": 0, "media_failed": 0, "errors": []}
                manifest, text = io.StringIO(), io.StringIO()
                with patch.object(tosint, "hash_file_sha256") as hashing:
                    accepted = tosint.process_download_message(message, app, 123, directory,
                        manifest, text, result, hash_media=True, media_index={})
                self.assertFalse(accepted)
                app.download_media.assert_not_called()
                hashing.assert_not_called()
                self.assertEqual(manifest.getvalue(), "")
                self.assertEqual(text.getvalue(), "")
                self.assertEqual(result["messages_filtered"], 1)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_dialog_identity_is_not_the_sender_identity(self):
        message = self.message(42)
        message.from_user = SimpleNamespace(id=999)
        self.assertTrue(tosint.message_matches_chat(message, 123))
        message.chat.id = 999
        message.sender_chat = SimpleNamespace(id=123)
        self.assertFalse(tosint.message_matches_chat(message, 123))

    def test_serializer_does_not_invent_chat_identity_from_the_requested_target(self):
        message = self.message(42, None)
        self.assertIsNone(tosint.message_to_json(message, chat_id=123)["chat_id"])


if __name__ == "__main__":
    unittest.main()
