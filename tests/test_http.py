import contextlib
import io
import json
import sys
import unittest
from unittest.mock import Mock, patch

import requests

import tosint


class BotAPIHTTPTests(unittest.TestCase):
    def response(self, status, payload):
        return Mock(status_code=status, json=Mock(return_value=payload))

    def test_success_and_timeout_configuration(self):
        payload = {"ok": True, "result": {"id": 123}}
        with patch("tosint.requests.request", return_value=self.response(200, payload)) as request:
            self.assertEqual(tosint.get_bot_info("secret"), payload)
        self.assertEqual(request.call_args.kwargs["timeout"], (10, 30))
        self.assertFalse(request.call_args.kwargs["allow_redirects"])

    def test_mutation_timeout_is_not_retried_or_leaked(self):
        with patch("tosint.requests.request", side_effect=requests.Timeout("URL with secret")) as request:
            with self.assertRaises(tosint.TelegramAPIError) as caught:
                tosint.send_message("secret", 123, ".")
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], "POST")
        self.assertNotIn("secret", str(caught.exception))

    def test_connection_error_is_sanitized(self):
        with patch("tosint.requests.request", side_effect=requests.ConnectionError("secret")):
            with self.assertRaisesRegex(tosint.TelegramAPIError, "transport error"):
                tosint.get_bot_info("secret")

    def test_telegram_error_response_preserves_parameters(self):
        payload = {"ok": False, "error_code": 400, "description": "migrated", "parameters": {"migrate_to_chat_id": -100123}}
        with patch("tosint.requests.request", return_value=self.response(400, payload)):
            self.assertEqual(tosint.get_bot_info("secret"), payload)

    def test_server_and_rate_limit_errors(self):
        for status, payload, expected in (
            (503, None, "server error"),
            (429, {"parameters": {"retry_after": 12}}, "Retry after 12 seconds"),
        ):
            with self.subTest(status=status), patch("tosint.requests.request", return_value=self.response(status, payload)):
                with self.assertRaisesRegex(tosint.TelegramAPIError, expected):
                    tosint.get_bot_info("secret")

    def test_invalid_json_and_unexpected_payload(self):
        responses = [self.response(200, []), self.response(200, {"ok": True}), self.response(302, {"ok": True, "result": {}})]
        invalid_json = self.response(502, None)
        invalid_json.status_code = 200
        invalid_json.json.side_effect = ValueError("HTML instead of JSON")
        responses.append(invalid_json)
        for response in responses:
            with self.subTest(response=response), patch("tosint.requests.request", return_value=response):
                with self.assertRaises(tosint.TelegramAPIError):
                    tosint.get_bot_info("secret")

    def test_cli_reports_failure_as_json_and_nonzero_exit(self):
        cases = (
            (self.response(401, {"ok": False, "error_code": 401, "description": "Unauthorized"}), "invalid or revoked"),
            (self.response(503, None), "server error"),
        )
        for response, expected in cases:
            output = io.StringIO()
            with self.subTest(expected=expected), patch.object(sys, "argv", ["tosint.py", "-t", "secret", "--json"]), patch("tosint.requests.request", return_value=response), contextlib.redirect_stdout(output):
                self.assertEqual(tosint.main(), 1)
            report = json.loads(output.getvalue())
            self.assertIn(expected, report["errors"][0])
            if expected == "server error":
                self.assertNotIn("revoked", report["errors"][0])

    def test_bot_only_success_has_zero_exit_and_no_chat_requests(self):
        methods = []

        def response_for(method, url, **kwargs):
            name = url.rsplit("/", 1)[-1]
            methods.append(name)
            result = {"id": 123, "first_name": "Example", "username": "example_bot", "can_read_all_group_messages": False} if name == "getMe" else ([] if name == "getMyCommands" else {})
            return self.response(200, {"ok": True, "result": result})

        output = io.StringIO()
        with patch.object(sys, "argv", ["tosint.py", "-t", "secret", "--json"]), patch("tosint.requests.request", side_effect=response_for), contextlib.redirect_stdout(output):
            self.assertEqual(tosint.main(), 0)
        self.assertEqual(json.loads(output.getvalue())["errors"], [])
        self.assertNotIn("getChatMember", methods)


if __name__ == "__main__":
    unittest.main()
