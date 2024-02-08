# tosint

Tosint (Telegram OSINT) is a tools to extract information from telegram bots and related associated channels.

Tosint allows you to extract the following information:

* Bot information (First Name, Username, User ID, Status);
* Chat information (Title, Type, ID, Username, Invite Link);
* Invite Link;  
* Number of users in the chat;
* Information about chat administrators.

### Example

```
$ python3 main.py
Telegram Token (bot1xxx): 562ZZZZ900:XXXXNj7_wIEi74GXXX90CIxACBIX_YYYYwI
Telegram Chat ID (-100xxx): -1001XXXXXX196

Analysis of token: 562ZZZZ900:XXXXNj7_wIEi74GXXX90CIxACBIX_YYYYwI and chat id: -1001XXXXXX196

Bot First Name: Over Security Bot
Bot Username: over_security_bot
Bot User ID: 56XXXXXX00
Bot Can Read Group Messages: False
Bot In The Chat Is An: administrator
Chat Title: Over Security
Chat Type: channel
Chat ID: -100XXXXXX3196
Chat has Visible History: True
Chat Username: OverSecurity
Chat Invite Link: https://t.me/+VmWXXXXXXHI1MTM0
Chat Invite Link (exported): https://t.me/+AqcXXXXXXGJmZjk0
Chat Invite Link (created): https://t.me/+LCsXXXXXXMgyYTg0
Number of users in the chat: 286
Administrators in the chat:
{'id': 56XXXXXX00, 'is_bot': True, 'first_name': 'Over Security Bot', 'username': 'over_security_bot'}
{'id': 20XXXX39, 'is_bot': False, 'first_name': 'Andrea', 'last_name': 'Draghetti', 'username': 'AndreaDraghetti'}
```

### License

GNU General Public License v3.0