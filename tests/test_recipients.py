import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pyrogram import enums

import test_chat_scope
import tosint


class RecipientMappingTests(unittest.TestCase):
    def message(self, message_id=1, chat_id=456, sender=123, outgoing=True, chat_type="private", date=None):
        return SimpleNamespace(
            id=message_id, chat=SimpleNamespace(id=chat_id, type=chat_type),
            from_user=SimpleNamespace(id=sender), outgoing=outgoing,
            date=date or datetime(2026, 11, 13, 12, tzinfo=timezone.utc),
            text="PRIVATE CONTENT", caption="PRIVATE CAPTION",
        )

    def test_unique_outgoing_messages_have_chronological_utc_ranges(self):
        recipients, seen = {}, set()
        latest = self.message(3, date=datetime(2026, 11, 13, 15, tzinfo=timezone(timedelta(hours=2))))
        earliest = self.message(1, chat_type=enums.ChatType.PRIVATE)
        middle = self.message(2, date=datetime(2026, 11, 13, 12, 30, tzinfo=timezone.utc))
        for message in (latest, earliest, middle, latest):
            tosint.record_recipient(message, 123, recipients, seen)
        self.assertEqual(recipients[456], {
            "chat_id": 456, "messages_observed": 3,
            "first_message_date": "2026-11-13T12:00:00Z",
            "last_message_date": "2026-11-13T13:00:00Z",
        })
        self.assertNotIn("PRIVATE", json.dumps(recipients))

    def test_unverifiable_incoming_self_and_nonprivate_messages_are_not_mapped(self):
        for overrides in (
            {"chat_id": None}, {"chat_id": "456"}, {"chat_id": True}, {"chat_id": -456},
            {"chat_id": 123}, {"sender": 999}, {"sender": "123"},
            {"outgoing": False}, {"outgoing": None}, {"outgoing": "true"},
            {"chat_type": "group"}, {"chat_type": "channel"}, {"chat_type": None},
            {"message_id": 0}, {"message_id": "1"}, {"date": "UNTRUSTED"},
        ):
            with self.subTest(overrides=overrides):
                recipients, seen = {}, set()
                tosint.record_recipient(self.message(**overrides), 123, recipients, seen)
                self.assertEqual(recipients, {})
                self.assertEqual(seen, set())
        message = self.message()
        message.date = None
        tosint.record_recipient(message, 123, {}, set())

    def test_bot_private_destinations_and_message_ids_shared_across_chats(self):
        recipients, seen = {}, set()
        for message in (self.message(), self.message(chat_id=999, chat_type=enums.ChatType.BOT)):
            tosint.record_recipient(message, 123, recipients, seen)
        self.assertEqual(set(recipients), {456, 999})
        self.assertEqual(len(seen), 2)

    def test_filtered_recipients_are_mapped_but_content_and_media_stay_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()
            foreign = self.message(6, chat_id=999)
            foreign.media = "document"
            foreign.document = SimpleNamespace(file_name="private.bin", file_unique_id="private", file_size=3)
            messages = {6: foreign, 5: self.message(5),
                        4: self.message(4, sender=456, outgoing=False),
                        3: self.message(3, chat_id=888, outgoing=False),
                        2: self.message(2, chat_id=None), 1: self.message(1)}
            app.get_messages.side_effect = lambda chat, ids, replies: [messages[i] for i in reversed(ids)]
            result, rows = test_chat_scope.ChatScopeTests().download(
                directory, app, target=456, resolved=456, map_recipients=True
            )
            self.assertEqual([row["message_id"] for row in rows], [5, 4, 1])
            self.assertFalse(Path(directory, "export", "media").exists())
            app.download_media.assert_not_called()
            app.get_chat.assert_called_once_with(456)
            app.get_messages.assert_called_once_with(456, [6, 5, 4, 3, 2, 1], replies=0)
        self.assertEqual(result["recipient_map"]["bot_id"], 123)
        self.assertEqual([(r["chat_id"], r["messages_observed"]) for r in result["recipient_map"]["recipients"]],
                         [(456, 2), (999, 1)])
        self.assertEqual(result["messages_filtered"], 3)
        self.assertEqual(result["media_failed"], 0)
        self.assertNotIn("PRIVATE", json.dumps(result["recipient_map"]))

    def test_interruption_preserves_partial_map_and_history_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Mock()

            def history(**kwargs):
                yield self.message(3, chat_id=999)
                yield self.message(3, chat_id=999)
                raise KeyboardInterrupt

            app.get_chat_history.side_effect = history
            result, rows = test_chat_scope.ChatScopeTests().download(
                directory, app, target=456, resolved=456, mode="history", auth="bot", map_recipients=True
            )
        self.assertTrue(result["interrupted"])
        self.assertEqual(rows, [])
        self.assertEqual(result["recipient_map"]["recipients"][0]["messages_observed"], 1)

    def test_mapping_is_disabled_by_default_and_does_not_change_export_limit(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as directory:
                app = Mock()
                app.get_messages.side_effect = lambda chat, ids, replies: [self.message(i) for i in ids]
                result, rows = test_chat_scope.ChatScopeTests().download(
                    directory, app, target=456, resolved=456, limit=2, map_recipients=enabled
                )
                self.assertEqual([row["message_id"] for row in rows], [6, 5])
                self.assertEqual("recipient_map" in result, enabled)
                if enabled:
                    self.assertEqual(result["recipient_map"]["recipients"][0]["messages_observed"], 2)

    def test_user_mapping_fails_before_import_or_directory_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "bot authentication"):
                tosint.download_chat_content(456, 1, "synthetic", str(Path(directory, "session", "user")),
                                             str(Path(directory, "export")), 0,
                                             download_auth_mode="user", map_recipients=True)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_map_round_trips_in_json_report_without_text_output(self):
        report = {"errors": [], "downloads": {"recipient_map": {
            "bot_id": 123, "coverage": "observed_outgoing_private_messages", "recipients": []}}}
        with patch.object(tosint, "TEXT_OUTPUT_ENABLED", False), patch("sys.stdout", new_callable=io.StringIO) as output:
            tosint.emit_json_report(report, True, None)
        self.assertEqual(json.loads(output.getvalue()), report)


if __name__ == "__main__":
    unittest.main()
