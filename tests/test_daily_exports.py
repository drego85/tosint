import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import tosint


class DailyExportTests(unittest.TestCase):
    stem = "2026.11.12_messages_example"

    def test_daily_stem_uses_local_date_sanitized_title_or_chat_id(self):
        day = date(2026, 11, 12)
        self.assertEqual(tosint.build_daily_messages_stem("Example / Chat", 123, day),
                         "2026.11.12_messages_example___chat")
        self.assertEqual(tosint.build_daily_messages_stem(None, 123, day),
                         "2026.11.12_messages_123")
        self.assertTrue(tosint.build_daily_messages_stem(None, 123).startswith(
            date.today().strftime("%Y.%m.%d") + "_messages_"))

    def test_overwrite_check_ignores_older_exports_and_shared_media(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(tosint.should_confirm_overwrite(directory, self.stem))
            Path(directory, "2026.11.11_messages_example.jsonl").touch()
            Path(directory, "messages_example.txt").touch()
            Path(directory, "media").mkdir()
            self.assertFalse(tosint.should_confirm_overwrite(directory, self.stem))
            for extension in ("jsonl", "txt"):
                target = Path(directory, f"{self.stem}.{extension}")
                target.touch()
                self.assertTrue(tosint.should_confirm_overwrite(directory, self.stem))
                target.unlink()

    def run_cli(self, directory, policy, current_exists=False, answer="y", result_extra=None):
        target = Path(directory, "example_bot", "456")
        target.mkdir(parents=True)
        Path(target, "2026.11.11_messages_example.jsonl").write_text("Previous day")
        if current_exists:
            Path(target, f"{self.stem}.jsonl").write_text("Earlier today")

        def api(token, method, params=None):
            values = {
                "getMe": {"id": 123, "first_name": "Example", "username": "example_bot",
                          "can_read_all_group_messages": False},
                "getChat": {"id": 456, "title": "Example", "type": "channel"},
                "getChatMember": {"status": "administrator"},
                "getChatMemberCount": 2,
                "getChatAdministrators": [], "getMyCommands": [],
            }
            return {"ok": True, "result": values.get(method, {})}

        result = {"download_mode_requested": "auto", "download_mode_used": "idscan",
                  "download_dir": str(target), "manifest_path": str(target / f"{self.stem}.jsonl"),
                  "text_path": str(target / f"{self.stem}.txt"), "messages_scanned": 1,
                  "unavailable_message_ids": 0, "messages_exported": 1,
                  "media_downloaded": 0, "media_failed": 0, "media_reused": 1}
        result.update(result_extra or {})
        with patch.object(sys, "argv", [
            "tosint.py", "-t", "123:fake", "-c", "456", "--download", "--json",
            "--api-id", "1", "--api-hash", "fake", "--download-dir", directory,
            "--download-overwrite", policy
        ]), patch.object(tosint, "load_env_file", return_value={}), patch.object(
            tosint, "telegram_api_get", side_effect=api
        ), patch.object(tosint, "build_daily_messages_stem", return_value=self.stem), patch.object(
            tosint, "download_chat_content", return_value=result
        ) as download, patch("builtins.input", return_value=answer) as prompt, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            status = tosint.main()
        self.assertEqual(Path(target, "2026.11.11_messages_example.jsonl").read_text(), "Previous day")
        return status, json.loads(output.getvalue()), download, prompt

    def test_first_export_of_new_day_never_prompts_even_with_never_policy(self):
        for policy in ("ask", "always", "never"):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as directory:
                status, _, download, prompt = self.run_cli(directory, policy)
                self.assertEqual(status, 0)
                download.assert_called_once()
                self.assertEqual(download.call_args.kwargs["output_stem"], self.stem)
                prompt.assert_not_called()

    def test_existing_today_export_honors_each_overwrite_policy(self):
        for policy, answer, proceed, prompted in (
            ("ask", "y", True, True), ("ask", "n", False, True),
            ("always", "n", True, False), ("never", "y", False, False),
        ):
            with self.subTest(policy=policy, answer=answer), tempfile.TemporaryDirectory() as directory:
                status, report, download, prompt = self.run_cli(directory, policy, True, answer)
                self.assertEqual(status, 0 if proceed else 1)
                self.assertEqual(download.call_count, int(proceed))
                self.assertEqual(prompt.call_count, int(prompted))
                self.assertEqual(bool(report["errors"]), not proceed)

    def test_additional_chat_skip_sets_failure_status_and_preserves_json_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            status, report, download, _ = self.run_cli(directory, "never", result_extra={
                "skipped_chats": [999], "messages_skipped_overwrite": 2,
            })
            self.assertEqual(status, 1)
            self.assertEqual(report["downloads"]["skipped_chats"], [999])
            self.assertEqual(len(report["errors"]), 1)
            self.assertEqual(download.call_args.kwargs["download_scope"], "token")
            self.assertEqual(download.call_args.kwargs["overwrite_policy"], "never")


if __name__ == "__main__":
    unittest.main()
