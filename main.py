#!/usr/bin/env python3
import sys
import telegram


def main():
    telegram_token = input("Telegram Token (bot1xxx): ").strip()
    telegram_chat_id = input("Telegram Chat ID (-100xxx): ").strip()

    if telegram_token.startswith("bot"):
        telegram_token = telegram_token[3:]

    print("\nAnalysis of token: " + str(telegram_token) + " and chat id: " + str(telegram_chat_id) + "\n")

    try:
        bot = telegram.Bot(telegram_token)
    except Exception as e:
        print("Error: " + str(e))
        bot = None
        exit()

    if bot:
        try:
            telegram_get_me = bot.getMe()

            print("Bot First Name: " + str(telegram_get_me["first_name"]))
            print("Bot Username: " + str(telegram_get_me["username"]))
        except:
            pass

        try:
            telegram_get_chat = bot.getChat(telegram_chat_id)
            print("Chat Title: " + str(telegram_get_chat["title"]))
            print("Chat Type: " + str(telegram_get_chat["type"]))
            print("Chat Invite Link: " + str(telegram_get_chat["invite_link"]))
        except:
            pass

        try:
            telegram_chat_invite_link = bot.exportChatInviteLink(telegram_chat_id)
            print("Chat Invite Link: " + str(telegram_chat_invite_link))
        except:
            pass

        try:
            telegram_get_updates = bot.getUpdates(telegram_chat_id)
            if telegram_get_updates:
                print("Updates:")
                for update in telegram_get_updates:
                    print(update["channel_post"])
        except:
            pass

        try:
            telegram_chat_members_count = bot.get_chat_member_count(telegram_chat_id)
            print("Number of users in the chat: " + str(telegram_chat_members_count))
        except:
            pass

        try:
            telegram_get_chat_administrators = bot.get_chat_administrators(telegram_chat_id)
            if telegram_get_chat_administrators:
                print("Users in the chat:")
                for user in telegram_get_chat_administrators:
                    print(user["user"])
        except:
            pass


if __name__ == "__main__":
    main()
