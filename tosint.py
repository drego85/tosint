#!/usr/bin/env python3
import argparse
import requests
import threading
import json
import yaml

# Base URL for Telegram API
TELEGRAM_API_URL = "https://api.telegram.org"


def get_bot_info(telegram_token):
    url = f"{TELEGRAM_API_URL}/bot{telegram_token}/getMe"
    response = requests.get(url)
    return response.json().get('result')


def get_chat_member_info(telegram_token, telegram_chat_id, bot_id):
    url = f"{TELEGRAM_API_URL}/bot{telegram_token}/getChatMember?chat_id={telegram_chat_id}&user_id={bot_id}"
    response = requests.get(url)
    return response.json()


def get_chat_info(telegram_token, telegram_chat_id):
    url = f"{TELEGRAM_API_URL}/bot{telegram_token}/getChat?chat_id={telegram_chat_id}"
    response = requests.get(url)
    return response.json().get('result')


def export_chat_invite_link(telegram_token, telegram_chat_id):
    url = f"{TELEGRAM_API_URL}/bot{telegram_token}/exportChatInviteLink?chat_id={telegram_chat_id}"
    response = requests.get(url)
    return response.json().get('result')


def create_chat_invite_link(telegram_token, telegram_chat_id):
    url = f"{TELEGRAM_API_URL}/bot{telegram_token}/createChatInviteLink?chat_id={telegram_chat_id}"
    response = requests.get(url)
    return response.json().get('result')


def get_chat_member_count(telegram_token, telegram_chat_id):
    url = f"{TELEGRAM_API_URL}/bot{telegram_token}/getChatMemberCount?chat_id={telegram_chat_id}"
    response = requests.get(url)
    return response.json().get('result')


def get_chat_administrators(telegram_token, telegram_chat_id):
    url = f"{TELEGRAM_API_URL}/bot{telegram_token}/getChatAdministrators?chat_id={telegram_chat_id}"
    response = requests.get(url)
    return response.json().get('result')


def format_output(data, output_format):
    if output_format == 'json':
        return json.dumps(data, indent=4)
    elif output_format == 'yaml':
        return yaml.dump(data, default_flow_style=False)
    else:
        raise ValueError("Unsupported format. Please choose 'json' or 'yaml'.")


def format_human_output(output_data):
    bot_info = output_data.get('bot_info') or {}
    chat_info = output_data.get('chat_info') or {}

    output = [
        f"Bot First Name: {bot_info.get('first_name', 'Not available')}",
        f"Bot Username: {bot_info.get('username', 'Not available')}",
        f"Bot User ID: {bot_info.get('id', 'Not available')}",
        f"Bot Can Read Group Messages: {bot_info.get('can_read_all_group_messages', 'Not available')}",
        f"Bot In The Chat Is An: {output_data.get('bot_chat_status', 'Not available')}",
        f"Chat Title: {chat_info.get('title', 'Not available')}",
        f"Chat Type: {chat_info.get('type', 'Not available')}",
        f"Chat ID: {chat_info.get('id', 'Not available')}",
        f"Chat has Visible History: {chat_info.get('has_linked_chat', 'Not available')}",
        f"Chat Username: {chat_info.get('username', 'Not available')}",
        f"Chat Invite Link: {chat_info.get('invite_link', 'Not available')}",
        f"Chat Invite Link (exported): {output_data.get('exported_chat_invite_link', 'Not available')}",
        f"Chat Invite Link (created): {output_data.get('created_chat_invite_link', 'Not available')}",
        f"Number of users in the chat: {output_data.get('chat_member_count', 'Not available')}",
        f"Administrators in the chat: {output_data.get('chat_administrators', 'Not available')}"
    ]

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description='OSINT analysis for Telegram bots.')

    parser.add_argument('-t', '--token', type=str, help='Telegram Token (bot1xxx)', required=False)
    parser.add_argument('-c', '--chat_id', type=str, help='Telegram Chat ID (-100xxx)', required=False)
    parser.add_argument('-o', '--output', type=str, choices=['json', 'yaml'],
                        help="Output format: 'json' or 'yaml'", required=False)

    args = parser.parse_args()

    telegram_token = args.token.strip() if args.token else input('Telegram Token (bot1xxx): ').strip()

    telegram_chat_id = args.chat_id.strip() if args.chat_id else input('Telegram Chat ID (-100xxx): ').strip()

    if telegram_token.startswith('bot'):
        telegram_token = telegram_token[3:]

    output_data = {}

    bot_info = get_bot_info(telegram_token)

    if bot_info:
        output_data['bot_info'] = {
            'first_name': bot_info['first_name'],
            'username': bot_info['username'],
            'id': bot_info['id'],
            'can_read_all_group_messages': bot_info.get('can_read_all_group_messages', 'Not available')
        }

        def get_member_info():
            output_data['bot_chat_status'] = get_chat_member_info(telegram_token, telegram_chat_id, bot_info['id']).get(
                'result', {}).get('status', 'N/A')

        def get_chat_info_thread():
            output_data['chat_info'] = get_chat_info(telegram_token, telegram_chat_id)

        def export_chat_link():
            output_data['exported_chat_invite_link'] = export_chat_invite_link(telegram_token, telegram_chat_id)

        def create_chat_link():
            output_data['created_chat_invite_link'] = create_chat_invite_link(telegram_token, telegram_chat_id)

        def chat_member_count():
            output_data['chat_member_count'] = get_chat_member_count(telegram_token, telegram_chat_id)

        def chat_administrators():
            output_data['chat_administrators'] = get_chat_administrators(telegram_token, telegram_chat_id)

        # Initialize and start threads
        threads = [
            threading.Thread(target=get_member_info),
            threading.Thread(target=get_chat_info_thread),
            threading.Thread(target=export_chat_link),
            threading.Thread(target=create_chat_link),
            threading.Thread(target=chat_member_count),
            threading.Thread(target=chat_administrators)
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        if args.output:
            if args.output in ['json', 'yaml']:
                print(format_output(output_data, args.output))
        else:
            print(format_human_output(output_data))
    else:
        print('Telegram token is invalid or revoked.')


if __name__ == '__main__':
    main()
