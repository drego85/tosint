import contextlib
import io
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
