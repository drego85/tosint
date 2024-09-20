# Tosint - Telegram OSINT Tool

Tosint (Telegram OSINT) is a tool designed to extract valuable information from Telegram bots and channels. 
It is ideal for security researchers, investigators, and anyone interested in gathering insights from Telegram entities. 
Using OSINT techniques, Tosint can uncover essential details about bots and associated channels, offering a deeper understanding of their structure and activity.

### Features

Tosint allows you to extract the following information:

- **Bot Information**: First Name, Username, User ID, Status, and whether the bot can read group messages.
- **Chat Information**: Chat Title, Type (group or channel), ID, Username, Invite Link.
- **Additional Information**:
    - Number of users in the chat.
    - Details of chat administrators, including their roles (e.g., admin, member).


### Use Cases

Tosint is a valuable tool for cybersecurity researchers involved in the analysis of malware or phishing kits. Cybercriminals increasingly use Telegram to collect information stolen from victims, such as: Malware logs, Login credentials, Credit or Debit Card details.

During investigations, by identifying the Token and Chat ID used by criminals (often found through malware or phishing kit analysis), Tosint enables the collection of valuable information to monitor the criminal activities. This helps researchers gain a clearer understanding of the infrastructure used by attackers, supporting a timely and targeted response to emerging threats.


### Who Uses Tosint?

Tosint has been adopted by security researchers, investigators, and professionals in the field of open-source intelligence (OSINT) to gather insights from Telegram bots and channels. 

I'm proud to mention that Tosint is also used by law enforcement agencies for investigative purposes, further demonstrating its practical value in real-world applications.

### Example Usage

To use Tosint, you can either provide the `Telegram Token` and `Chat ID` interactively, or pass them as command-line arguments.

**Interactive Mode**:
```
$ python3 tosint.py
Telegram Token (bot1xxx): 562ZZZZ900:XXXXNj7_wIEi74GXXX90CIxACBIX_YYYYwI
Telegram Chat ID (-100xxx): -1001XXXXXX196
```

**Command-Line Arguments**:
```
$ python3 tosint.py -t 562ZZZZ900:XXXXNj7_wIEi74GXXX90CIxACBIX_YYYYwI -c -1001XXXXXX196
```

Both approaches will provide you with detailed information about the bot and chat.

### Example Output

After running the tool, the following is an example of the output you can expect:

```

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

### Installation

1. Clone the repository:
```
git clone https://github.com/drego85/tosint.git
```

2. Install the required dependencies:
```
pip install -r requirements.txt
```

3. Run the tool:
```
python3 tosint.py
```

Make sure you have Python 3.x installed.

### Contributing and Supporting the Project

There are two ways you can contribute to the development of **Tosint**:

1. **Development Contributions**:

   Please ensure that your code follows best practices and includes relevant tests.

2. **Donation Support**:
   If you find this project useful and would like to support its development, you can also make a donation via [Buy Me a Coffee](https://buymeacoffee.com/andreadraghetti). Your support is greatly appreciated and helps to keep this project going!

   [![Buy Me a Coffee](https://img.shields.io/badge/-Buy%20Me%20a%20Coffee-orange?logo=buy-me-a-coffee&logoColor=white&style=flat-square)](https://buymeacoffee.com/andreadraghetti)

### License

This project is licensed under the GNU General Public License v3.0.