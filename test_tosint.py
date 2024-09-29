import unittest
import requests_mock
import json
from tosint import (
    get_bot_info, get_chat_member_info, get_chat_info, export_chat_invite_link,
    create_chat_invite_link, get_chat_member_count, get_chat_administrators,
    format_output, format_human_output
)

TELEGRAM_API_URL = "https://api.telegram.org"

MOCK_TELEGRAM_TOKEN = "123456:ABCDEF"
MOCK_CHAT_ID = "-100123456789"
MOCK_BOT_INFO = {
    "ok": True,
    "result": {
        "id": 123456789,
        "is_bot": True,
        "first_name": "TestBot",
        "username": "testbot"
    }
}
MOCK_CHAT_INFO = {
    "ok": True,
    "result": {
        "id": MOCK_CHAT_ID,
        "type": "supergroup",
        "title": "Test Chat",
        "has_linked_chat": True,
        "username": "testchat"  # Added for completeness
    }
}
MOCK_CHAT_MEMBER_INFO = {
    "ok": True,
    "result": {
        "status": "administrator"
    }
}
MOCK_CHAT_MEMBER_COUNT = {
    "ok": True,
    "result": 100
}
MOCK_ADMINISTRATORS = {
    "ok": True,
    "result": [{"user": {"id": 123456789, "first_name": "Admin"}}]
}
MOCK_INVITE_LINK = {
    "ok": True,
    "result": "https://t.me/joinchat/abc123"
}


class TestTelegramBotScript(unittest.TestCase):
    @requests_mock.Mocker()
    def test_get_bot_info(self, mock_request):
        url = f"{TELEGRAM_API_URL}/bot{MOCK_TELEGRAM_TOKEN}/getMe"
        mock_request.get(url, json=MOCK_BOT_INFO)

        bot_info = get_bot_info(MOCK_TELEGRAM_TOKEN)
        self.assertEqual(bot_info['username'], "testbot")
        self.assertEqual(bot_info['id'], 123456789)

    @requests_mock.Mocker()
    def test_get_chat_member_info(self, mock_request):
        url = f"{TELEGRAM_API_URL}/bot{MOCK_TELEGRAM_TOKEN}/getChatMember?chat_id={MOCK_CHAT_ID}&user_id=123456789"
        mock_request.get(url, json=MOCK_CHAT_MEMBER_INFO)

        member_info = get_chat_member_info(MOCK_TELEGRAM_TOKEN, MOCK_CHAT_ID, 123456789)
        self.assertEqual(member_info['result']['status'], "administrator")

    @requests_mock.Mocker()
    def test_get_chat_info(self, mock_request):
        url = f"{TELEGRAM_API_URL}/bot{MOCK_TELEGRAM_TOKEN}/getChat?chat_id={MOCK_CHAT_ID}"
        mock_request.get(url, json=MOCK_CHAT_INFO)

        chat_info = get_chat_info(MOCK_TELEGRAM_TOKEN, MOCK_CHAT_ID)
        self.assertEqual(chat_info['title'], "Test Chat")
        self.assertEqual(chat_info['id'], MOCK_CHAT_ID)

    @requests_mock.Mocker()
    def test_export_chat_invite_link(self, mock_request):
        url = f"{TELEGRAM_API_URL}/bot{MOCK_TELEGRAM_TOKEN}/exportChatInviteLink?chat_id={MOCK_CHAT_ID}"
        mock_request.get(url, json=MOCK_INVITE_LINK)

        invite_link = export_chat_invite_link(MOCK_TELEGRAM_TOKEN, MOCK_CHAT_ID)
        self.assertEqual(invite_link, "https://t.me/joinchat/abc123")

    @requests_mock.Mocker()
    def test_create_chat_invite_link(self, mock_request):
        url = f"{TELEGRAM_API_URL}/bot{MOCK_TELEGRAM_TOKEN}/createChatInviteLink?chat_id={MOCK_CHAT_ID}"
        mock_request.get(url, json=MOCK_INVITE_LINK)

        invite_link = create_chat_invite_link(MOCK_TELEGRAM_TOKEN, MOCK_CHAT_ID)
        self.assertEqual(invite_link, "https://t.me/joinchat/abc123")

    @requests_mock.Mocker()
    def test_get_chat_member_count(self, mock_request):
        url = f"{TELEGRAM_API_URL}/bot{MOCK_TELEGRAM_TOKEN}/getChatMemberCount?chat_id={MOCK_CHAT_ID}"
        mock_request.get(url, json=MOCK_CHAT_MEMBER_COUNT)

        member_count = get_chat_member_count(MOCK_TELEGRAM_TOKEN, MOCK_CHAT_ID)
        self.assertEqual(member_count, 100)

    @requests_mock.Mocker()
    def test_get_chat_administrators(self, mock_request):
        url = f"{TELEGRAM_API_URL}/bot{MOCK_TELEGRAM_TOKEN}/getChatAdministrators?chat_id={MOCK_CHAT_ID}"
        mock_request.get(url, json=MOCK_ADMINISTRATORS)

        administrators = get_chat_administrators(MOCK_TELEGRAM_TOKEN, MOCK_CHAT_ID)
        self.assertEqual(administrators[0]['user']['first_name'], "Admin")

    def test_format_output(self):
        data = {"key": "value"}

        # Test JSON output
        json_output = format_output(data, 'json')
        self.assertEqual(json.loads(json_output), data)

        # Test YAML output
        yaml_output = format_output(data, 'yaml')
        self.assertTrue('key: value' in yaml_output)

    def test_invalid_format_output(self):
        data = {"key": "value"}
        with self.assertRaises(ValueError):
            format_output(data, 'invalid_format')

    def test_format_human_output(self):
        output_data = {
            'bot_info': {
                'first_name': 'TestBot',
                'username': 'testbot',
                'id': 123456789,
                'can_read_all_group_messages': False
            },
            'bot_chat_status': 'administrator',
            'chat_info': {
                'title': 'Test Chat',
                'type': 'supergroup',
                'id': MOCK_CHAT_ID,
                'has_linked_chat': True,
                'username': 'testchat',
                'invite_link': "https://t.me/joinchat/abc123"
            },
            'exported_chat_invite_link': "https://t.me/joinchat/abc123",
            'created_chat_invite_link': "https://t.me/joinchat/abc123",
            'chat_member_count': 100,
            'chat_administrators': [{'user': {'id': 123456789, 'first_name': 'Admin'}}]
        }

        expected_output = (
            "Bot First Name: TestBot\n"
            "Bot Username: testbot\n"
            "Bot User ID: 123456789\n"
            "Bot Can Read Group Messages: False\n"
            "Bot In The Chat Is An: administrator\n"
            "Chat Title: Test Chat\n"
            "Chat Type: supergroup\n"
            "Chat ID: -100123456789\n"
            "Chat has Visible History: True\n"
            "Chat Username: testchat\n"
            "Chat Invite Link: https://t.me/joinchat/abc123\n"
            "Chat Invite Link (exported): https://t.me/joinchat/abc123\n"
            "Chat Invite Link (created): https://t.me/joinchat/abc123\n"
            "Number of users in the chat: 100\n"
            "Administrators in the chat: [{'user': {'id': 123456789, 'first_name': 'Admin'}}]"
        )

        human_output = format_human_output(output_data)
        self.assertEqual(human_output, expected_output)


if __name__ == '__main__':
    unittest.main()
