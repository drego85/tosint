#!/usr/bin/env python3
import argparse
import requests

def main():
    # Initialize the argument parser for command-line parameters
    parser = argparse.ArgumentParser(description='OSINT analysis for Telegram bots.')

    # Add options for token and chat ID
    parser.add_argument('-t', '--token', type=str, help='Telegram Token (bot1xxx)', required=False)
    parser.add_argument('-c', '--chat_id', type=str, help='Telegram Chat ID (-100xxx)', required=False)

    # Parse the command-line arguments
    args = parser.parse_args()

    # If the token is not provided via command line, prompt the user for input
    if args.token:
        telegram_token = args.token.strip()
    else:
        telegram_token = input('Telegram Token (bot1xxx): ').strip()

    # If the chat ID is not provided via command line, prompt the user for input
    if args.chat_id:
        telegram_chat_id = args.chat_id.strip()
    else:
        telegram_chat_id = input('Telegram Chat ID (-100xxx): ').strip()

    # Remove the 'bot' prefix from the token if it exists
    if telegram_token.startswith('bot'):
        telegram_token = telegram_token[3:]

    print(f"\nAnalysis of token: {telegram_token} and chat id: {telegram_chat_id}\n")

    # Get Bot Info
    url = f"https://api.telegram.org/bot{telegram_token}/getMe"
    response = requests.get(url)
    telegram_get_me = response.json().get('result')

    # If the response contains bot information, print the relevant details
    if telegram_get_me:
       
        print(f"Bot First Name: {telegram_get_me['first_name']}")
        print(f"Bot Username: {telegram_get_me['username']}")
        print(f"Bot User ID: {telegram_get_me['id']}")
        print(f"Bot Can Read Group Messages: {telegram_get_me['can_read_all_group_messages']}")

        # Get Bot Status - Member or Admin

        url = f"https://api.telegram.org/bot{telegram_token}/getChatMember?chat_id={telegram_chat_id}&user_id={telegram_get_me['id']}"
        response = requests.get(url)
        if response.json().get('result'):
            telegram_get_chat_member = response.json().get('result')
            print(f"Bot In The Chat Is An: {telegram_get_chat_member['status']}")
        elif response.json().get('description'):
            if response.json().get('parameters') and 'migrate_to_chat_id' in response.json().get('parameters'): 
                print(f"ATTENTION {response.json().get('description')} - Migrated to: {response.json().get('parameters')['migrate_to_chat_id']}")
            else:
                print(f"ATTENTION {response.json().get('description')}")

        # Get Chat Info

        url = f"https://api.telegram.org/bot{telegram_token}/getChat?chat_id={telegram_chat_id}"
        response = requests.get(url)
        telegram_get_chat = response.json().get('result')

        if 'title' in telegram_get_chat: print(f"Chat Title: {telegram_get_chat['title']}")
        print(f"Chat Type: {telegram_get_chat['type']}")
        print(f"Chat ID: {telegram_get_chat['id']}")
        if 'has_visible_history' in telegram_get_chat: print(f"Chat has Visible History: {telegram_get_chat['has_visible_history']}")
        if 'username' in telegram_get_chat: print(f"Chat Username: {telegram_get_chat['username']}")
        if 'invite_link' in telegram_get_chat: print(f"Chat Invite Link: {telegram_get_chat['invite_link']}")


        # Export Chat Invite Link

        url = f"https://api.telegram.org/bot{telegram_token}/exportChatInviteLink?chat_id={telegram_chat_id}"
        response = requests.get(url)
        telegram_chat_invite_link = response.json().get("result")

        print(f"Chat Invite Link (exported): {telegram_chat_invite_link}")

        # Create Chat Invite Link

        url = f"https://api.telegram.org/bot{telegram_token}/createChatInviteLink?chat_id={telegram_chat_id}"
        response = requests.get(url)
        telegram_chat_invite_link = response.json().get('result')

        if "invite_link" in telegram_get_chat: print(f"Chat Invite Link (created): {telegram_chat_invite_link['invite_link']}")

        # Get Chat Member Count

        url = f"https://api.telegram.org/bot{telegram_token}/getChatMemberCount?chat_id={telegram_chat_id}"
        response = requests.get(url)
        telegram_chat_members_count = response.json().get('result')

        print(f"Number of users in the chat: {telegram_chat_members_count}")

        # Get Administrators in chat

        url = f"https://api.telegram.org/bot{telegram_token}/getChatAdministrators?chat_id={telegram_chat_id}"
        response = requests.get(url)
        telegram_get_chat_administrators = response.json().get('result')

        if telegram_get_chat_administrators:
            print(f"Administrators in the chat:")
            for user in telegram_get_chat_administrators:
                print(user['user'])
    else:
        print('Telegram token is invalid or revoked.')


if __name__ == '__main__':
    main()