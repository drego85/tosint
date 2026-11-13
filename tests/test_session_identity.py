import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import tosint


class SessionIdentityTests(unittest.TestCase):
    def download(self, directory, identity, auth="bot", expected=123, token="123:fake"):
        app = Mock()
        app.me = identity
        app.get_chat.return_value = SimpleNamespace(title="Example", type="group")
        message = SimpleNamespace(id=1, date=datetime(2026, 11, 10), text="Example")
        app.get_messages.return_value = [message]
        app.get_chat_history.return_value = iter([message])
        pyrogram = ModuleType("pyrogram")
        pyrogram.Client = Mock(return_value=app)
        errors = ModuleType("pyrogram.errors")
        errors.SessionRevoked = type("SessionRevoked", (Exception,), {})
        self.app = app
        self.client_factory = pyrogram.Client
        with patch.dict(sys.modules, {"pyrogram": pyrogram, "pyrogram.errors": errors}):
            return tosint.download_chat_content(
                456, 1, "fake", str(Path(directory, "custom")),
                str(Path(directory, "export")), 0, start_message_id=1,
                bot_token_for_auth=token, download_auth_mode=auth,
                expected_bot_id=expected, progress_every=0
            )

    def test_matching_bot_session_records_verified_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.download(directory, SimpleNamespace(id=123, is_bot=True))
            self.assertEqual(result["authenticated_user_id"], 123)
            self.assertTrue(result["authenticated_is_bot"])
            self.assertEqual(result["messages_exported"], 1)
        self.app.start.assert_called_once()
        self.app.stop.assert_called_once()
        self.assertEqual(self.client_factory.call_args.kwargs["workdir"], os.getcwd())

    def test_matching_user_session_does_not_require_the_bot_user_id(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.download(directory, SimpleNamespace(id=789, is_bot=False), auth="user")
        self.assertEqual(result["authenticated_user_id"], 789)
        self.assertFalse(result["authenticated_is_bot"])
        self.app.get_chat_history.assert_called_once()

    def test_mismatches_preserve_session_and_evidence_without_chat_requests(self):
        for auth, identity in (
            ("bot", SimpleNamespace(id=999, is_bot=True)),
            ("bot", SimpleNamespace(id=123, is_bot=False)),
            ("user", SimpleNamespace(id=123, is_bot=True)),
        ):
            with self.subTest(auth=auth, identity=identity), tempfile.TemporaryDirectory() as directory:
                session = Path(directory, "custom.session")
                with sqlite3.connect(session) as database:
                    database.executescript(
                        "CREATE TABLE version (number INTEGER); INSERT INTO version VALUES (7);"
                        "CREATE TABLE sessions (dc_id, api_id, auth_key, user_id, is_bot, server_address, port);"
                        "CREATE TABLE usernames (id, username);"
                    )
                previous_session = session.read_bytes()
                export_dir = Path(directory, "export")
                export_dir.mkdir()
                previous = export_dir / "messages_example.jsonl"
                previous.write_text("previous evidence")
                with self.assertRaisesRegex(RuntimeError, "Session identity mismatch"):
                    self.download(directory, identity, auth=auth)
                self.assertEqual(session.read_bytes(), previous_session)
                self.assertEqual(previous.read_text(), "previous evidence")
                self.assertEqual(list(export_dir.glob(".acquisition-*")), [])
                self.app.get_chat.assert_not_called()
                self.app.get_messages.assert_not_called()
                self.app.get_chat_history.assert_not_called()
                self.app.stop.assert_called_once()
                self.client_factory.assert_called_once()

    def test_missing_or_malformed_cached_identity_fails_closed(self):
        for identity in (None, SimpleNamespace(id=123), SimpleNamespace(id="123", is_bot=True)):
            with self.subTest(identity=identity), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(RuntimeError, "Unable to verify"):
                    self.download(directory, identity)
                self.assertFalse(Path(directory, "export").exists())
                self.app.get_chat.assert_not_called()
                self.app.stop.assert_called_once()

    def test_expected_bot_id_can_be_derived_from_token_for_direct_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.download(directory, SimpleNamespace(id=123, is_bot=True),
                                   expected=None, token="bot123:fake")
        self.assertEqual(result["authenticated_user_id"], 123)

    def test_invalid_token_id_is_rejected_before_opening_a_session(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "expected bot ID"):
                self.download(directory, SimpleNamespace(id=123, is_bot=True),
                              expected=None, token="invalid")
            self.client_factory.assert_not_called()
            self.assertFalse(Path(directory, "export").exists())

    def test_cli_passes_bot_api_identity_to_download(self):
        def api(token, method, params=None):
            results = {
                "getMe": {"id": 123, "first_name": "Example", "username": "example_bot",
                          "can_read_all_group_messages": False},
                "getChat": {"id": 456, "type": "private"},
                "getChatMember": {"status": "member"},
                "getChatMemberCount": 2,
                "getMyCommands": [],
            }
            return {"ok": True, "result": results.get(method, {})}

        result = {
            "download_mode_requested": "auto", "download_mode_used": "idscan",
            "download_dir": "export", "manifest_path": "export/messages.jsonl",
            "text_path": "export/messages.txt", "messages_scanned": 1,
            "unavailable_message_ids": 0, "messages_exported": 1,
            "media_downloaded": 0, "media_failed": 0,
        }
        with tempfile.TemporaryDirectory() as directory, patch.object(sys, "argv", [
            "tosint.py", "-t", "123:fake", "-c", "456", "--download", "--json",
            "--api-id", "1", "--api-hash", "fake", "--download-dir", directory
        ]), patch.object(tosint, "load_env_file", return_value={}), patch.object(
            tosint, "telegram_api_get", side_effect=api
        ), patch.object(tosint, "download_chat_content", return_value=result) as download, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(tosint.main(), 0)
        self.assertEqual(download.call_args.kwargs["expected_bot_id"], 123)
        self.assertEqual(json.loads(output.getvalue())["errors"], [])


if __name__ == "__main__":
    unittest.main()
