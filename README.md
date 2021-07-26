# tosint

Tosint (Telegram OSINT) is a tools to extract information from telegram bots and related associated channels.

Tosint allows you to extract the following information:

* Bot information (First Name, Username);
* Chat information (Title, Type, Invite Link);
* Updates (last messages sent in the chat);
* Number of users in the chat;
* Information about chat administrators.

### Example

```
$ python3 main.py
Telegram Token (bot1xxx): 15968583XX:XXXXXXX_WhUt9sarlxIPZRXXXXX
Telegram Chat ID (-100xxx): -10XXXXX862846

Analysis of token: 15968583XX:XXXXXXX_WhUt9sarlxIPZRXXXXX and chat id: -10XXXXX862846

Bot First Name: siXXben
Bot Username: simXXXXbot
Chat Title: CaXXX
Chat Type: channel
Chat Invite Link: https://t.me/joinchat/wGM1_XXXXcU2Mzdk
Chat Invite Link: https://t.me/joinchat/7hyptXXXXXg1MDI8
Number of users in the chat: 3
Administrators in the chat:
{'id': 159XXX8335, 'is_bot': True, 'first_name': 'siXXben', 'username': 'simXXXXbot'}
{'id': 919XXX436, 'is_bot': False, 'first_name': 'SXXXi', 'last_name': 'VXXX', 'language_code': 'ar', 'username': 'SimXXXX201'}
```

### License

GNU General Public License v3.0