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
