import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tosint


class CLIValidationTests(unittest.TestCase):
    def test_download_scope_defaults_follow_authentication(self):
        for options, expected in (([], "token"), (["--download-auth", "user"], "chatid"),
                                  (["--download-scope", "chatid"], "chatid")):
            with self.subTest(options=options), patch.object(sys, "argv", ["tosint.py", "-t", "fake", *options]), patch.object(
                tosint, "run_analysis"
            ) as analysis:
                self.assertEqual(tosint.main(), 0)
                self.assertEqual(analysis.call_args.args[0].download_scope, expected)

    def test_user_authentication_rejects_token_scope_before_analysis(self):
        with patch.object(sys, "argv", ["tosint.py", "-t", "fake", "--download-auth", "user", "--download-scope", "token"]), patch.object(
            tosint, "run_analysis"
        ) as analysis, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                tosint.main()
        self.assertEqual(caught.exception.code, 2)
        analysis.assert_not_called()

    def test_recipient_mapping_requires_download_and_bot_auth_before_analysis(self):
        for options in (["--map-recipients"], ["--download", "-c", "456", "--map-recipients", "--download-auth", "user"]):
            with self.subTest(options=options), patch.object(sys, "argv", ["tosint.py", "-t", "fake", *options]), patch.object(
                tosint, "run_analysis"
            ) as analysis, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    tosint.main()
                self.assertEqual(caught.exception.code, 2)
                analysis.assert_not_called()

    def test_recipient_mapping_accepts_both_download_aliases(self):
        for option in ("--download", "--downloads"):
            with self.subTest(option=option), patch.object(sys, "argv", [
                "tosint.py", "-t", "fake", "-c", "456", option, "--map-recipients"
            ]), patch.object(tosint, "run_analysis") as analysis:
                self.assertEqual(tosint.main(), 0)
                self.assertTrue(analysis.call_args.args[0].map_recipients)

    def test_scope_diagnostics_flag_is_passed_to_analysis(self):
        with patch.object(sys, "argv", ["tosint.py", "-t", "fake", "--download-debug-scope"]), patch.object(
            tosint, "run_analysis"
        ) as analysis:
            self.assertEqual(tosint.main(), 0)
        self.assertTrue(analysis.call_args.args[0].download_debug_scope)

    def test_invalid_download_ranges_are_rejected_before_analysis(self):
        for option, value in (
            ("--download-start-id", "0"),
            ("--download-start-id", "-5"),
            ("--download-limit", "-1"),
        ):
            with self.subTest(option=option, value=value), patch.object(
                sys, "argv", ["tosint.py", "-t", "fake", option, value]
            ), patch.object(tosint, "run_analysis") as analysis, contextlib.redirect_stderr(
                io.StringIO()
            ) as stderr:
                with self.assertRaises(SystemExit) as caught:
                    tosint.main()
                self.assertEqual(caught.exception.code, 2)
                self.assertIn(option, stderr.getvalue())
                analysis.assert_not_called()

    def test_positive_start_and_unlimited_export_are_accepted(self):
        with patch.object(sys, "argv", [
            "tosint.py", "-t", "fake", "--download-start-id", "1", "--download-limit", "0"
        ]), patch.object(tosint, "run_analysis") as analysis:
            self.assertEqual(tosint.main(), 0)
        args = analysis.call_args.args[0]
        self.assertEqual(args.download_start_id, 1)
        self.assertEqual(args.download_limit, 0)


class JSONReportTests(unittest.TestCase):
    def test_credentials_and_library_output_use_stderr_in_json_mode(self):
        def analysis(args, report):
            print("Synthetic library login banner")
            report["api_id_received"] = tosint.get_value(None, {}, prompt_text="Telegram API_ID: ")
            report["api_hash_received"] = tosint.get_value(None, {}, prompt_text="Telegram API_HASH: ")

        with patch.object(sys, "argv", ["tosint.py", "-t", "fake", "--json"]), patch.object(
            tosint, "run_analysis", side_effect=analysis
        ), patch("sys.stdin", io.StringIO("1\nsynthetic\n")), contextlib.redirect_stdout(io.StringIO()) as output, \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = tosint.main()
        self.assertEqual(status, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["api_id_received"], "1")
        self.assertEqual(report["api_hash_received"], "synthetic")
        self.assertIn("Synthetic library login banner", stderr.getvalue())
        self.assertIn("Telegram API_ID:", stderr.getvalue())
        self.assertIn("Telegram API_HASH:", stderr.getvalue())

    def test_stdout_is_restored_after_analysis_error_or_interruption(self):
        for error, expected in ((tosint.TelegramAPIError("Synthetic failure"), 1), (KeyboardInterrupt(), 130)):
            with self.subTest(error=type(error).__name__), patch.object(sys, "argv", ["tosint.py", "-t", "fake", "--json"]), \
                    patch.object(tosint, "run_analysis", side_effect=error), \
                    contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(tosint.main(), expected)
                self.assertTrue(json.loads(output.getvalue())["errors"])

    def test_non_json_mode_keeps_interactive_output_on_stdout(self):
        def analysis(args, report):
            print("Synthetic banner")
            tosint.get_value(None, {}, prompt_text="Synthetic prompt: ")

        with patch.object(sys, "argv", ["tosint.py", "-t", "fake"]), patch.object(tosint, "run_analysis", side_effect=analysis), \
                patch("sys.stdin", io.StringIO("answer\n")), contextlib.redirect_stdout(io.StringIO()) as output, \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(tosint.main(), 0)
        self.assertIn("Synthetic banner", output.getvalue())
        self.assertIn("Synthetic prompt:", output.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_missing_prompt_input_returns_none_without_corrupting_json_output(self):
        with patch.object(tosint, "TEXT_OUTPUT_ENABLED", False), patch("sys.stdin", io.StringIO()), \
                contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertIsNone(tosint.get_value(None, {}, prompt_text="Synthetic prompt: "))
        self.assertEqual(output.getvalue(), "")
        self.assertIn("Synthetic prompt:", stderr.getvalue())

    def test_stdout_includes_report_save_failure_and_exit_is_nonzero(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(sys, "argv", [
            "tosint.py", "-t", "fake", "--json", "--json-file", directory
        ]), patch.object(tosint, "run_analysis"), contextlib.redirect_stdout(io.StringIO()) as output:
            exit_code = tosint.main()
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(output.getvalue())["errors"], ["Unable to save JSON report."])

    def test_saved_and_stdout_json_match_when_save_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory, "report.json")
            with patch.object(sys, "argv", [
                "tosint.py", "-t", "fake", "--json", "--json-file", str(destination)
            ]), patch.object(tosint, "run_analysis"), contextlib.redirect_stdout(io.StringIO()) as output:
                exit_code = tosint.main()
            saved = json.loads(destination.read_text())
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(output.getvalue()), saved)
        self.assertEqual(saved["errors"], [])

    def test_file_only_save_failure_is_recorded_without_stdout_json(self):
        report = {"errors": []}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            tosint, "TEXT_OUTPUT_ENABLED", False
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            tosint.emit_json_report(report, False, directory)
        self.assertEqual(report["errors"], ["Unable to save JSON report."])
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
