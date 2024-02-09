#!/usr/bin/env python3
import requests

def main():
    telegram_token = input("Telegram Token (bot1xxx): ").strip()
    telegram_chat_id = input("Telegram Chat ID (-100xxx): ").strip()

    if telegram_token.startswith("bot"):
        telegram_token = telegram_token[3:]

    print("\nAnalysis of token: " + str(telegram_token) + " and chat id: " + str(telegram_chat_id) + "\n")

    # Get Bot Info

    url = f"https://api.telegram.org/bot{telegram_token}/getMe"
    response = requests.get(url)
    telegram_get_me = response.json().get("result")
       
    print("Bot First Name: " + str(telegram_get_me["first_name"]))
    print("Bot Username: " + str(telegram_get_me["username"]))
    print("Bot User ID: " + str(telegram_get_me["id"]))
    print("Bot Can Read Group Messages: " + str(telegram_get_me["can_read_all_group_messages"]))
    url = f"https://api.telegram.org/bot{telegram_token}/getChatMember?chat_id={telegram_chat_id}&user_id={telegram_get_me['id']}"
    response = requests.get(url)
    telegram_get_chat_member = response.json().get("result")
    print("Bot In The Chat Is An: " + telegram_get_chat_member["status"])

    # Get Chat Info

    url = f"https://api.telegram.org/bot{telegram_token}/getChat?chat_id={telegram_chat_id}"
    response = requests.get(url)
    telegram_get_chat = response.json().get("result")

    if "title" in telegram_get_chat: print("Chat Title: " + str(telegram_get_chat["title"]))
    print("Chat Type: " + str(telegram_get_chat["type"]))
    print("Chat ID: " + str(telegram_get_chat["id"]))
    if "has_visible_history" in telegram_get_chat: print("Chat has Visible History: " + str(telegram_get_chat["has_visible_history"]))
    if "username" in telegram_get_chat: print("Chat Username: " + str(telegram_get_chat["username"]))
    if "invite_link" in telegram_get_chat: print("Chat Invite Link: " + str(telegram_get_chat["invite_link"]))


    # Export Chat Invite Link

    url = f"https://api.telegram.org/bot{telegram_token}/exportChatInviteLink?chat_id={telegram_chat_id}"
    response = requests.get(url)
    telegram_chat_invite_link = response.json().get("result")

    print("Chat Invite Link (exported): " + str(telegram_chat_invite_link))

    # Create Chat Invite Link

    url = f"https://api.telegram.org/bot{telegram_token}/createChatInviteLink?chat_id={telegram_chat_id}"
    response = requests.get(url)
    telegram_chat_invite_link = response.json().get("result")

    print("Chat Invite Link (created): " + str(telegram_chat_invite_link["invite_link"]))

    # Get Chat Member Count

    url = f"https://api.telegram.org/bot{telegram_token}/getChatMemberCount?chat_id={telegram_chat_id}"
    response = requests.get(url)
    telegram_chat_members_count = response.json().get("result")

    print("Number of users in the chat: " + str(telegram_chat_members_count))

    # Get Administrators in chat

    url = f"https://api.telegram.org/bot{telegram_token}/getChatAdministrators?chat_id={telegram_chat_id}"
    response = requests.get(url)
    telegram_get_chat_administrators = response.json().get("result")

    if telegram_get_chat_administrators:
        print("Administrators in the chat:")
        for user in telegram_get_chat_administrators:
            print(user["user"])



if __name__ == "__main__":
    main()