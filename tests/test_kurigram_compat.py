import asyncio
import inspect
import io
import json
import os
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pyrogram
from pyrogram import Client, enums, raw, types, utils
from pyrogram.crypto import aes

import tosint


class KurigramCompatibilityTests(unittest.TestCase):
    def test_kurigram_owns_the_namespace_without_conflicting_distributions(self):
        self.assertEqual(pyrogram.__version__, version("kurigram"))
        for package in ("pyrofork", "Pyrogram"):
            with self.subTest(package=package), self.assertRaises(PackageNotFoundError):
                version(package)

    def client(self):
        app = Client("offline-test", api_id=1, api_hash="synthetic", in_memory=True)
        app.me = types.User(id=123, first_name="Example", is_bot=True)
        app.resolve_peer = AsyncMock(return_value=raw.types.InputPeerUser(user_id=456, access_hash=0))
        app.invoke = AsyncMock(return_value=raw.types.messages.Messages(
            messages=[raw.types.Message(
                id=42, peer_id=raw.types.PeerUser(user_id=456), date=1784116800,
                message="Example", entities=[], restriction_reason=[],
                from_id=raw.types.PeerUser(user_id=123)
            ), raw.types.MessageEmpty(id=41)], topics=[], chats=[], users=[
                raw.types.User(id=123, first_name="Example", bot=True, usernames=[], restriction_reason=[]),
                raw.types.User(id=456, first_name="Other", usernames=[], restriction_reason=[])
            ]
        ))
        return app

    def test_sync_batch_uses_real_parser_and_preserves_empty_message_ids(self):
        app = self.client()
        messages = app.get_messages(456, [42, 41], replies=0)
        self.assertFalse(inspect.isawaitable(messages))
        self.assertEqual([message.id for message in messages], [42, 41])
        self.assertEqual(messages[0].text, "Example")
        self.assertTrue(messages[1].empty)
        self.assertIsNone(messages[1].date)
        app.invoke.assert_awaited_once()

    def test_history_remains_synchronously_iterable(self):
        app = self.client()
        self.assertEqual([message.id for message in app.get_chat_history(456, limit=1)], [42])
        app.invoke.assert_awaited_once()

    def test_real_private_batch_can_include_another_dialog_but_export_filters_it(self):
        app = self.client()
        app.invoke.return_value.messages.append(raw.types.Message(
            id=40, peer_id=raw.types.PeerUser(user_id=999), date=1784116800,
            message="Foreign dialog content", out=True, entities=[], restriction_reason=[],
            from_id=raw.types.PeerUser(user_id=123)
        ))
        app.invoke.return_value.users.append(raw.types.User(
            id=999, first_name="Foreign", usernames=[], restriction_reason=[]
        ))
        messages = app.get_messages(456, [42, 41, 40], replies=0)
        self.assertIsInstance(app.invoke.call_args.args[0], raw.functions.messages.GetMessages)
        self.assertEqual([message.chat.id for message in messages if message.date], [456, 999])
        manifest, text = io.StringIO(), io.StringIO()
        result = {"messages_exported": 0, "media_downloaded": 0, "media_failed": 0, "errors": []}
        with tempfile.TemporaryDirectory() as directory:
            for message in messages:
                tosint.process_download_message(message, Mock(), 456, directory, manifest, text, result)
        self.assertEqual(result["messages_exported"], 1)
        self.assertEqual(result["messages_filtered"], 1)
        self.assertEqual(json.loads(manifest.getvalue())["chat_id"], 456)
        self.assertNotIn("Foreign dialog content", manifest.getvalue())
        self.assertNotIn("Foreign dialog content", text.getvalue())

    @unittest.skipUnless(hasattr(time, "tzset"), "Requires process timezone control")
    def test_actual_library_dates_convert_to_utc_in_winter_and_summer(self):
        try:
            with patch.dict(os.environ, {"TZ": "Europe/Rome"}):
                time.tzset()
                for month in (1, 7):
                    with self.subTest(month=month):
                        expected = datetime(2026, month, 15, 12, tzinfo=timezone.utc)
                        local = utils.timestamp_to_datetime(int(expected.timestamp()))
                        self.assertIsNone(local.tzinfo)
                        self.assertEqual(tosint.format_utc_datetime(local),
                                         expected.isoformat().replace("+00:00", "Z"))
        finally:
            time.tzset()

    def test_real_media_objects_preserve_export_metadata(self):
        message = types.Message(
            id=42, date=utils.timestamp_to_datetime(1784116800),
            chat=types.Chat(id=-1000000000456, type=enums.ChatType.SUPERGROUP),
            media=enums.MessageMediaType.DOCUMENT, caption="Example",
            document=types.Document(file_id="synthetic", file_unique_id="unique", file_size=3,
                                    file_name="archive.zip", mime_type="application/zip")
        )
        payload = tosint.message_to_json(message)
        self.assertEqual(json.loads(json.dumps(payload))["media_type"], "MessageMediaType.DOCUMENT")
        self.assertEqual(payload["file_unique_id"], "unique")
        self.assertEqual(payload["telegram_file_size"], 3)
        self.assertEqual(payload["original_file_name"], "archive.zip")
        self.assertEqual(tosint.media_reuse_key(message.media, "unique", 3), ("document", "unique", 3))

    def test_tgcrypto_backend_remains_available(self):
        self.assertEqual(aes._crypto_backend.__name__.lower(), "tgcrypto")
        key, iv, data = bytes(range(32)), bytes(range(32)), bytes(range(64))
        self.assertEqual(aes.ige256_decrypt(aes.ige256_encrypt(data, key, iv), key, iv), data)

    def test_default_start_does_not_request_qr_authorization(self):
        self.assertFalse(inspect.signature(Client.start).parameters["use_qr"].default)


class KurigramSessionFormatTests(unittest.TestCase):
    def test_default_paths_are_separate_from_old_pyrofork_paths(self):
        for mode in ("bot", "user"):
            self.assertEqual(tosint.build_scoped_session_name(None, -123, "example_bot", mode),
                             str(Path("sessions", "kurigram", "example_bot_-123", mode)))
        self.assertEqual(tosint.build_scoped_session_name("custom/session", -123), "custom/session")

    def test_missing_session_is_left_for_new_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            name = str(Path(directory, "new"))
            tosint.check_session_format(name)
            self.assertFalse(Path(f"{name}.session").exists())

    def test_relative_client_session_uses_the_explicit_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Client("sessions/kurigram/example/bot", api_id=1, api_hash="synthetic", workdir=directory)
            self.assertEqual(Path(app.storage.database),
                             Path(directory, "sessions", "kurigram", "example", "bot.session"))

    def test_actual_new_kurigram_database_passes_read_only_check(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Client("fresh", api_id=1, api_hash="synthetic", workdir=directory)

            async def create():
                await app.storage.open()
                await app.storage.close()

            asyncio.run(create())
            path = Path(directory, "fresh.session")
            before = path.read_bytes()
            tosint.check_session_format(str(Path(directory, "fresh")))
            self.assertEqual(path.read_bytes(), before)

    def test_legacy_format_is_rejected_before_client_or_export_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            name = str(Path(directory, "legacy #?"))
            path = Path(f"{name}.session")
            with sqlite3.connect(path) as database:
                database.executescript(
                    "CREATE TABLE version (number INTEGER); INSERT INTO version VALUES (4);"
                    "CREATE TABLE sessions (dc_id, api_id, auth_key, user_id, is_bot);"
                    "CREATE TABLE usernames (id, peer_id);"
                )
            before = path.read_bytes()
            with patch("pyrogram.Client") as client:
                with self.assertRaisesRegex(RuntimeError, "Use a new --session-name"):
                    tosint.download_chat_content(123, 1, "synthetic", name,
                        str(Path(directory, "export")), 0, bot_token_for_auth="123:synthetic")
            client.assert_not_called()
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(Path(directory, "export").exists())

    def test_version_number_alone_does_not_make_an_incompatible_schema_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            name = str(Path(directory, "wrong-schema"))
            with sqlite3.connect(f"{name}.session") as database:
                database.executescript("CREATE TABLE version (number INTEGER); INSERT INTO version VALUES (7);")
            with self.assertRaisesRegex(RuntimeError, "Incompatible saved session format"):
                tosint.check_session_format(name)


if __name__ == "__main__":
    unittest.main()
