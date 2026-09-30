import contextlib
import io
import unittest
from unittest.mock import patch

import tosint


class BotIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.responses = {
            "getWebhookInfo": {"url": "https://example.org/webhook", "ip_address": "203.0.113.10", "pending_update_count": 0, "has_custom_certificate": False},
            "getMyCommands": [{"command": "start", "description": "Start the bot"}],
            "getChatMenuButton": {"type": "web_app", "text": "Dashboard", "web_app": {"url": "https://example.org/dashboard"}},
        }

    def collect(self, api):
        report = {"bot": {}, "errors": []}
        output = io.StringIO()
        with patch.object(tosint, "telegram_api_get", side_effect=api), patch.object(tosint, "TEXT_OUTPUT_ENABLED", True), contextlib.redirect_stdout(output):
            tosint.enrich_bot_info("fake", report)
        return report, output.getvalue()

    def test_results_preserved_and_useful_fields_displayed(self):
        report, output = self.collect(lambda token, method: {"ok": True, "result": self.responses[method]})
        self.assertEqual(report["bot"]["webhook"], self.responses["getWebhookInfo"])
        self.assertEqual(report["bot"]["commands"], self.responses["getMyCommands"])
        self.assertEqual(report["bot"]["menu_button"], self.responses["getChatMenuButton"])
        self.assertIn("https://example.org/webhook", output)
        self.assertIn("/start: Start the bot", output)
        self.assertIn("https://example.org/dashboard", output)
        self.assertIn("Bot Pending Updates Awaiting Delivery: 0", output)
        self.assertEqual(report["errors"], [])

    def test_empty_commands_and_no_webhook_are_not_errors(self):
        self.responses["getWebhookInfo"] = {"url": "", "pending_update_count": 0}
        self.responses["getMyCommands"] = []
        self.responses["getChatMenuButton"] = {"type": "commands"}
        report, output = self.collect(lambda token, method: {"ok": True, "result": self.responses[method]})
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["bot"]["commands"], [])
        self.assertIn("Not configured", output)
        self.assertIn("Bot Default Menu Button Type: commands", output)

    def capture_output(self, function, *args):
        output = io.StringIO()
        with patch.object(tosint, "TEXT_OUTPUT_ENABLED", True), contextlib.redirect_stdout(output):
            function(*args)
        return output.getvalue()

    def test_chat_labels_preserve_the_scope_of_api_flags(self):
        chat = {"is_direct_messages": True, "has_visible_history": True,
                "has_hidden_members": True, "join_by_request": True,
                "join_to_send_messages": True, "permissions": {"can_send_messages": False},
                "pinned_message": {"message_id": 42, "date": 123}}
        output = self.capture_output(tosint.print_chat_summary, chat)
        for label in ("Chat Is Channel Direct Messages", "Chat History Visible To New Members",
                      "Chat Member List Hidden From Non-Administrators",
                      "Direct Join Requires Admin Approval (without invite link)",
                      "Membership Required To Send Messages", "Default Chat Member Permissions",
                      "Most Recent Pinned Message (by send date)", "Sent Date (Unix timestamp)"):
            self.assertIn(label + ":", output)

    def test_invite_labels_do_not_claim_unreturned_links_do_not_exist(self):
        self.assertEqual(self.capture_output(tosint.print_invite_links, None, None).strip(),
                         "Invite Links: Not returned by Telegram")
        output = self.capture_output(tosint.print_invite_links, "primary", "additional")
        self.assertIn("Primary Chat Invite Link: primary", output)
        self.assertIn("Additional Chat Invite Link (created): additional", output)

    def test_admin_attributes_are_not_labelled_only_as_permissions(self):
        member = {"user": {"id": 123}, "status": "administrator",
                  "can_be_edited": False, "is_anonymous": True, "can_delete_messages": True}
        output = self.capture_output(tosint.print_admin_details, member, 1)
        self.assertIn("Chat Membership Status: administrator", output)
        self.assertIn("Administrator Rights and Attributes:", output)
        self.assertEqual(tosint.build_admin_json(member, 1)["permissions"],
                         tosint.extract_admin_permissions(member))

    def test_api_and_transport_failures_do_not_stop_other_enrichment(self):
        for transport in (False, True):
            def api(token, method):
                if method == "getWebhookInfo":
                    if transport:
                        raise tosint.TelegramAPIError("getWebhookInfo: request timed out")
                    return {"ok": False, "description": "Forbidden"}
                return {"ok": True, "result": self.responses[method]}
            with self.subTest(transport=transport):
                report, _ = self.collect(api)
                self.assertEqual(len(report["errors"]), 1)
                self.assertNotIn("webhook", report["bot"])
                self.assertIn("commands", report["bot"])
                self.assertIn("menu_button", report["bot"])

    def test_admin_lookup_includes_other_bots(self):
        with patch.object(tosint, "telegram_api_get", return_value={"ok": True, "result": []}) as api:
            tosint.get_chat_administrators("fake", -123)
        api.assert_called_once_with("fake", "getChatAdministrators", params={"chat_id": -123, "return_bots": "true"})


if __name__ == "__main__":
    unittest.main()
